"""
Phase 2b: Test splitting singular_vision into two sub-dimensions.
- First evaluates on a 200-script sample (~$3)
- If promising, rolls out to all 909 (~$14)
"""
import json
import os
from pathlib import Path
from datetime import datetime
import random
from typing import Dict, List, Tuple


class FacetSplitter:
    """Propose and test splitting high-gap facets"""

    def __init__(self):
        pass

    def generate_split_proposal(self) -> Dict:
        """Generate a proposal to split singular_vision into two sub-dimensions"""
        return {
            "split_type": "singular_vision → 2 sub-facets",
            "original_facet": "singular_vision",
            "new_facets": [
                "authorial_distinctiveness",  # Unique voice, perspective, cinematic sensibility
                "premise_audacity"            # Boldness of the central concept
            ],
            "rationale": "singular_vision conflates two things: distinctive authorial voice (execution) and audacious concept (idea). Splitting these might provide more signal.",
            "sample_size": 200,
            "sample_cost": "$3.00",
            "rollout_cost": "$14.00",
            "total_cost_if_rollout": "$17.00"
        }

    def create_evaluation_prompt(self) -> str:
        """Return the prompt to evaluate the two sub-dimensions"""
        return """
You are evaluating a TV pilot script for two specific dimensions of "singular vision":

1. **AUTHORIAL_DISTINCTIVENESS** (1-10 scale):
   - Does the script have a recognizable, distinctive authorial voice?
   - Evidence: unique perspectives, recurring motifs, signature cinematic choices, distinctive dialogue patterns, original sensibilities
   - A 9-10 means: you could identify this writer from a blind page. The style, perspective, and sensibility are unmistakable.
   - A 1-3 means: the script feels generic, like it could have been written by many writers.

2. **PREMISE_AUDACITY** (1-10 scale):
   - How audacious, unexpected, or bold is the central premise/concept?
   - Evidence: high concept hook, willingness to take risks with genre/tone/protagonist, unconventional premise structures
   - A 9-10 means: the premise is genuinely surprising or daring. Most networks would balk at this central idea.
   - A 1-3 means: the premise is safe, familiar, or procedural. It's been done before.

Return a JSON object with:
{
  "authorial_distinctiveness": <1-10 score>,
  "authorial_reasoning": "<2-3 sentence explanation>",
  "premise_audacity": <1-10 score>,
  "premise_reasoning": "<2-3 sentence explanation>"
}
"""

    def print_proposal(self):
        """Print the split proposal"""
        proposal = self.generate_split_proposal()
        print("\n" + "="*100)
        print("PHASE 2b: SPLIT SINGULAR_VISION INTO TWO SUB-DIMENSIONS")
        print("="*100 + "\n")

        print(f"Proposal: {proposal['split_type']}")
        print(f"Original facet: {proposal['original_facet']}")
        print(f"New facets: {proposal['new_facets']}")
        print(f"\nRationale: {proposal['rationale']}")
        print(f"\nApproach:")
        print(f"  1. Sample 200 scripts from holdout + tune set")
        print(f"  2. Evaluate both new sub-facets via LLM")
        print(f"  3. Compare: 1 facet (singular_vision) vs 2 sub-facets (authorial + premise)")
        print(f"  4. If sub-facets improve holdout accuracy, roll out to all 909 scripts")
        print(f"\nCosts:")
        print(f"  Sample evaluation: {proposal['sample_cost']}")
        print(f"  Full rollout (if promising): {proposal['rollout_cost']}")
        print(f"  Total if promoted: {proposal['total_cost_if_rollout']}")
        print("\n" + "="*100 + "\n")

    def create_sample(self, benchmark_path: str, results_dir: str, sample_size: int = 200) -> List[str]:
        """Create a stratified sample for testing"""
        benchmark = {}
        with open(benchmark_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    script_id = entry.get("script_id")
                    label = entry.get("label")
                    if script_id and label in ["winner", "loser"]:
                        benchmark[script_id] = label
                except:
                    pass

        winners = [sid for sid, label in benchmark.items() if label == "winner"]
        losers = [sid for sid, label in benchmark.items() if label == "loser"]

        # Stratified sample: maintain winner/loser ratio
        total_scripts = len(winners) + len(losers)
        winner_ratio = len(winners) / total_scripts
        sample_winners = int(sample_size * winner_ratio)
        sample_losers = sample_size - sample_winners

        sample = (
            random.sample(winners, min(sample_winners, len(winners))) +
            random.sample(losers, min(sample_losers, len(losers)))
        )

        # Save sample
        sample_path = os.path.join(results_dir, "facet_split_sample.json")
        with open(sample_path, "w") as f:
            json.dump({
                "sample_size": len(sample),
                "script_ids": sample,
                "winners": sum(1 for sid in sample if benchmark.get(sid) == "winner"),
                "losers": sum(1 for sid in sample if benchmark.get(sid) == "loser"),
            }, f, indent=2)

        print(f"Created sample of {len(sample)} scripts ({sample_winners} winners, {sample_losers} losers)")
        print(f"Sample saved to facet_split_sample.json")

        return sample

    def generate_split_evaluation_instructions(self, sample_ids: List[str]) -> str:
        """Generate instructions for evaluating the split on a sample"""
        return f"""
INSTRUCTIONS FOR PHASE 2b: SPLIT SINGULAR_VISION

You have {len(sample_ids)} scripts in a sample (from both holdout and tune sets).

For each script:
1. Load the extracted text
2. Evaluate two NEW sub-dimensions:
   - authorial_distinctiveness: How recognizable is the writer's voice?
   - premise_audacity: How bold/audacious is the central concept?
3. Store results in per_script JSON files with structure:
   {{
     "script_id": "...",
     "aggregated": {{
       "individual_scores": {{
         "authorial_distinctiveness": <score>,
         "premise_audacity": <score>,
         ...other facets...
       }}
     }}
   }}

Sample script IDs to evaluate:
{json.dumps(sample_ids[:10], indent=2)}
... (and {len(sample_ids) - 10} more)

This sample evaluation costs approximately $3 and will determine if the split is worth rolling out to all 909 scripts ($14 more).
"""


if __name__ == "__main__":
    splitter = FacetSplitter()
    splitter.print_proposal()

    # For now, just demonstrate the capability
    # In practice, this would trigger LLM evaluation
    print("Phase 2b would:")
    print("  1. Create a 200-script stratified sample")
    print("  2. Evaluate authorial_distinctiveness + premise_audacity on sample")
    print("  3. Test if 2-facet split outperforms 1-facet singular_vision on holdout")
    print("  4. If >0.5% improvement, roll out to all 909 scripts")
    print("  5. Compare full 8-facet config (6 original + 2 new) vs current 6-facet best")
