"""
RubricMutator: Proposes targeted mutations to the v2.0 scoring rubric.

Uses gpt-5-mini to generate candidate rubric variants based on:
  - Dimension gap analysis (which dims discriminate winners vs losers)
  - Score variance analysis (which dims score inconsistently)
  - Optimizer weight findings (which dims got zeroed out)

Mutation types:
  - tighten_anchors:  Sharpen the 1/5/10 scoring examples for a noisy dimension
  - reframe:          Rewrite a dimension with a tighter/different focus
  - replace:          Swap a weak dimension for a completely new one
  - split:            Break one dimension into two more precise sub-dimensions
  - merge:            Combine two correlated dimensions into one
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Diagnosis hard-coded from our gap analysis findings
# (so the mutator knows what's wrong without recomputing)
DIMENSION_DIAGNOSIS = {
    "creative_originality_and_boldness": {
        "status": "noisy",
        "problem": (
            "Highest raw winner/loser gap (1.751) but optimizer zeroes it out (weight ~0.05). "
            "This means the LLM scores losers inconsistently on this dimension — some losers "
            "score very high, creating false positives. The scoring anchors are too subjective. "
            "Fix: make the question more concrete and tied to specific, observable script attributes."
        ),
        "std_winner": 0.958,
        "std_loser": 1.904,
        "gap": 1.751,
        "optimizer_weight": 0.05,
    },
    "narrative_momentum_engagement": {
        "status": "weak_discriminator",
        "problem": (
            "Lowest winner/loser gap (1.281) among all 5 dimensions. Also heavily downweighted "
            "by the optimizer (0.35). The dimension may be too generic — most competently written "
            "scripts will score reasonably on 'engagement'. "
            "Fix: reframe around pilot-specific compulsion (does ep 1 CREATE the need for ep 2?) "
            "rather than general narrative quality."
        ),
        "std_winner": 0.69,
        "std_loser": 1.975,
        "gap": 1.281,
        "optimizer_weight": 0.35,
    },
    "audience_appeal_marketability": {
        "status": "strong",
        "problem": "Performing well. Optimizer weight: 3.0. Low winner variance (0.564). No fix needed.",
        "std_winner": 0.564,
        "std_loser": 1.847,
        "gap": 1.466,
        "optimizer_weight": 3.0,
    },
    "character_appeal_and_long_term_potential": {
        "status": "strong",
        "problem": "Performing well. Optimizer weight: 2.85. High winner average (8.58). No fix needed.",
        "std_winner": 0.806,
        "std_loser": 1.955,
        "gap": 1.634,
        "optimizer_weight": 2.85,
    },
    "conceptual_hook_clarity": {
        "status": "strong",
        "problem": "Performing well. Optimizer weight: 2.15. Very tight winner scoring (std 0.556). No fix needed.",
        "std_winner": 0.556,
        "std_loser": 2.064,
        "gap": 1.389,
        "optimizer_weight": 2.15,
    },
}


MUTATION_SYSTEM_PROMPT = """You are an expert in TV development and script evaluation systems.

You are helping improve an automated script scoring system that evaluates TV pilots to identify transcendent shows.

The system uses 5 dimensions scored 1-10. The current system achieves 84% pairwise ranking accuracy (separating transcendent shows like Breaking Bad, The Sopranos, Fleabag from produced-but-forgettable shows).

Your job: propose specific rubric mutations to fix identified problems. You will be given:
1. The CURRENT rubric text for a specific dimension
2. A DIAGNOSIS of what's wrong with it
3. The MUTATION TYPE requested

Requirements for your mutations:
- Must produce more CONSISTENT scores across similar-quality scripts (reduce variance)
- Must better SEPARATE winners (transcendent shows) from losers (forgettable shows)
- Must be grounded in things a PRODUCER would actually recognize in a script
- Must NOT introduce prestige bias (e.g., don't reward "literary" or "arthouse" qualities)
- Must be applicable across ALL genres (comedy, drama, thriller, sci-fi, etc.)
- Must have concrete 1/5/10 examples using real shows: Breaking Bad, Seinfeld, The Office, Sopranos, I Love Lucy, Game of Thrones, Fleabag, The Wire, The Simpsons, Stranger Things

Return ONLY valid JSON with this structure:
{
  "mutation_type": "tighten_anchors|reframe|replace|split",
  "dimension_name": "...",
  "new_dimension_name": "...",  // same or new name
  "rationale": "...",  // 2-3 sentences on why this is better
  "rubric_text": "..."  // COMPLETE rubric text for this dimension (replaces the old section)
}

The rubric_text must follow this exact format:
### [N]. [Dimension Name] (1-10)

**What it measures:** [one sentence]

**Strong signals (7-10):**
- [bullet]
...

**Weak signals (1-6):**
- [bullet]
...

**Scoring anchors:**
- 9-10: [concrete example with show name]
- 7-8: [concrete example with show name]
- 5-6: [concrete example with show name]
- 3-4: [concrete example with show name]
- 1-2: [concrete example with show name]

**Examples:**
- [Show] ([score]): [1 sentence justification]
...
"""


class RubricMutator:
    """Generates targeted rubric mutations using LLM."""

    def __init__(self, rubric_path: str, gap_analysis_path: str):
        self.rubric_path = Path(rubric_path)
        self.gap_analysis_path = Path(gap_analysis_path)
        self.rubric_text = self.rubric_path.read_text()

        import openai
        self.client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    def _extract_dimension_section(self, dimension_name: str) -> str:
        """Extract the rubric section for a specific dimension."""
        dim_display = {
            "audience_appeal_marketability": "Audience Appeal",
            "conceptual_hook_clarity": "Conceptual Hook",
            "character_appeal_and_long_term_potential": "Character Appeal",
            "creative_originality_and_boldness": "Creative Originality",
            "narrative_momentum_engagement": "Narrative Momentum",
        }
        search = dim_display.get(dimension_name, dimension_name)

        lines = self.rubric_text.split("\n")
        in_section = False
        section_lines = []

        for i, line in enumerate(lines):
            if search.lower() in line.lower() and line.startswith("###"):
                in_section = True
            elif in_section and line.startswith("###") and search.lower() not in line.lower():
                break
            if in_section:
                section_lines.append(line)

        return "\n".join(section_lines)

    def propose_mutations(self, target_dimensions: List[str] = None,
                          mutation_types: List[str] = None,
                          n_variants: int = 3) -> List[Dict]:
        """
        Generate rubric mutations for target dimensions.

        Args:
            target_dimensions: Which dims to mutate. Defaults to the two weakest.
            mutation_types: Which mutation types to try. Defaults to ["tighten_anchors", "reframe", "replace"]
            n_variants: Number of variants to generate per (dimension, mutation_type) combo

        Returns:
            List of mutation dicts, each containing the new dimension rubric text
        """
        if target_dimensions is None:
            # Default to the two problematic dimensions
            target_dimensions = ["creative_originality_and_boldness", "narrative_momentum_engagement"]

        if mutation_types is None:
            mutation_types = ["tighten_anchors", "reframe", "replace"]

        mutations = []

        for dim in target_dimensions:
            diagnosis = DIMENSION_DIAGNOSIS.get(dim, {})
            current_section = self._extract_dimension_section(dim)

            for mut_type in mutation_types:
                for variant_idx in range(n_variants):
                    logger.info(f"Proposing {mut_type} for {dim} (variant {variant_idx + 1})...")
                    mutation = self._call_llm_for_mutation(
                        dim, current_section, diagnosis, mut_type, variant_idx
                    )
                    if mutation:
                        mutation["source_dimension"] = dim
                        mutation["variant_idx"] = variant_idx
                        mutation["timestamp"] = datetime.utcnow().isoformat()
                        mutations.append(mutation)

        return mutations

    def _call_llm_for_mutation(self, dimension: str, current_section: str,
                                diagnosis: Dict, mutation_type: str, variant_idx: int) -> Optional[Dict]:
        """Call gpt-5-mini to generate a single rubric mutation."""
        type_instructions = {
            "tighten_anchors": (
                "TIGHTEN ANCHORS mutation: Keep the same dimension concept but rewrite the scoring "
                "anchors (1/5/10 examples) to be much more CONCRETE and OBSERVABLE. "
                "The anchors should be based on specific, checkable script attributes, "
                "not subjective judgments. A trained analyst should give this dimension "
                "consistent scores across similar-quality scripts."
            ),
            "reframe": (
                "REFRAME mutation: Rewrite this dimension with a tighter, more precise focus. "
                "The core concept can stay similar, but the framing should make it harder "
                "for mediocre scripts to score high (fewer false positives) while still "
                "rewarding genuinely transcendent shows. Think like a network exec deciding "
                "whether to put $50M into development."
            ),
            "replace": (
                f"REPLACE mutation (variant {variant_idx + 1}): This dimension is underperforming. "
                "Replace it with a COMPLETELY NEW dimension that would better separate transcendent "
                "shows from merely competent ones. Think about what producers ACTUALLY look for "
                "that the current 5 dimensions miss. Consider: episode engine clarity, "
                "franchise/IP potential, world-building distinctiveness, tonal commitment, "
                "casting clarity, or genre-redefining potential."
            ),
        }

        user_prompt = f"""## Dimension to Improve: `{dimension}`

## Current Rubric Section:
{current_section}

## Diagnosis (what's wrong):
{diagnosis.get('problem', 'No diagnosis available')}

## Statistical Problem:
- Winner average: {diagnosis.get('gap', 0) + 6:.2f}, Loser average: ~6.0
- Winner std dev: {diagnosis.get('std_winner', 0):.3f}
- Loser std dev: {diagnosis.get('std_loser', 0):.3f}  ← HIGH VARIANCE IN LOSERS
- Optimizer weight assigned: {diagnosis.get('optimizer_weight', 0):.2f} (lower = less trusted)

## Mutation Type:
{type_instructions.get(mutation_type, mutation_type)}

Generate the mutation now. Return ONLY valid JSON."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-5-mini",
                messages=[
                    {"role": "system", "content": MUTATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_completion_tokens=1500,
            )
            raw = response.choices[0].message.content.strip()

            # Parse JSON
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]

            mutation = json.loads(raw)
            mutation["mutation_type"] = mutation_type
            return mutation

        except Exception as e:
            logger.error(f"Failed to generate mutation for {dimension}/{mutation_type}: {e}")
            return None

    def build_candidate_rubric(self, mutation: Dict) -> str:
        """
        Build a complete candidate rubric by substituting one mutated dimension.

        Args:
            mutation: Mutation dict with 'source_dimension' and 'rubric_text'

        Returns:
            Full candidate rubric text
        """
        source_dim = mutation["source_dimension"]
        new_section = mutation["rubric_text"]
        dim_display = {
            "audience_appeal_marketability": "Audience Appeal",
            "conceptual_hook_clarity": "Conceptual Hook",
            "character_appeal_and_long_term_potential": "Character Appeal",
            "creative_originality_and_boldness": "Creative Originality",
            "narrative_momentum_engagement": "Narrative Momentum",
        }
        search = dim_display.get(source_dim, source_dim)

        lines = self.rubric_text.split("\n")
        out_lines = []
        skip = False

        for i, line in enumerate(lines):
            if search.lower() in line.lower() and line.startswith("###"):
                skip = True
                out_lines.append(new_section)
            elif skip and line.startswith("###") and search.lower() not in line.lower():
                skip = False
                out_lines.append(line)
            elif not skip:
                out_lines.append(line)

        return "\n".join(out_lines)

    def save_mutations(self, mutations: List[Dict], output_path: str):
        """Save proposed mutations to JSON."""
        with open(output_path, "w") as f:
            json.dump(mutations, f, indent=2)
        logger.info(f"Saved {len(mutations)} mutations → {output_path}")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    mutator = RubricMutator(
        rubric_path="./config/rubric_prompt.md",
        gap_analysis_path="./data/results/v2_gap_analysis.json",
    )

    mutations = mutator.propose_mutations(
        target_dimensions=["creative_originality_and_boldness", "narrative_momentum_engagement"],
        mutation_types=["tighten_anchors", "reframe", "replace"],
        n_variants=1,
    )

    print(f"\nGenerated {len(mutations)} mutations")
    for m in mutations:
        print(f"  - {m['mutation_type']} for {m['source_dimension']}: {m.get('rationale', '')[:80]}")

    mutator.save_mutations(mutations, "./data/results/rubric_mutations_proposed.json")
