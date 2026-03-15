"""Phase 4: Script analysis pipeline.

Runs structured factor analysis on scripts using Claude API.
Outputs structured JSON with versioned prompts.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

from factors import factors_as_prompt_context, get_default_factors, get_factor_names
from models import FactorScore, LinkedRecord, ScriptAnalysis

PROMPT_VERSION = "v1"
ANALYSIS_VERSION = "v1"

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert TV script analyst working for a research project studying what makes TV shows succeed or fail.

You will analyze a TV pilot script and score it on specific factors. For each factor, provide:
1. A score from 1-10
2. A confidence level from 0.0-1.0 (how confident you are in your assessment)
3. Specific evidence from the script supporting your score
4. Brief notes on anything notable

Be rigorous and honest. Avoid grade inflation — use the full 1-10 range. A score of 5 is average/neutral.

IMPORTANT: Base your scores ONLY on what's in the script text provided. Do not use knowledge of whether the show succeeded or failed. Analyze the script as if you don't know the outcome."""


def build_analysis_prompt(script_text: str, show_title: str, episode_title: Optional[str] = None) -> str:
    """Build the full analysis prompt for a script."""
    factor_context = factors_as_prompt_context()

    ep_info = f" — Episode: {episode_title}" if episode_title else ""

    return f"""Analyze the following TV pilot script for: **{show_title}**{ep_info}

## Factors to Score

{factor_context}

## Script Text

<script>
{script_text}
</script>

## Output Format

Respond with ONLY a JSON object in this exact format:
{{
  "scores": [
    {{
      "factor_name": "premise_strength",
      "score": 7,
      "confidence": 0.8,
      "evidence": "The pilot establishes a clear 'what if' in the first scene...",
      "notes": ""
    }},
    // ... one entry per factor
  ]
}}

Score ALL {len(get_default_factors())} factors: {', '.join(get_factor_names())}"""


# ---------------------------------------------------------------------------
# Analysis execution
# ---------------------------------------------------------------------------

def analyze_script_with_claude(
    script_text: str,
    show_title: str,
    episode_title: Optional[str] = None,
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-20250514",
    max_script_chars: int = 150_000,
) -> ScriptAnalysis:
    """Analyze a single script using the Claude API."""
    try:
        import anthropic
    except ImportError:
        raise ImportError("Install anthropic: pip install anthropic")

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    # Truncate very long scripts
    if len(script_text) > max_script_chars:
        script_text = script_text[:max_script_chars] + "\n\n[TRUNCATED — script exceeded character limit]"

    prompt = build_analysis_prompt(script_text, show_title, episode_title)

    client = anthropic.Anthropic(api_key=key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )

    # Parse response
    response_text = response.content[0].text.strip()

    # Extract JSON from response (handle markdown code blocks)
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()

    data = json.loads(response_text)
    scores = [FactorScore(**s) for s in data["scores"]]

    return ScriptAnalysis(
        show_title=show_title,
        episode_title=episode_title,
        script_filename="",
        factor_scores=scores,
        analysis_version=ANALYSIS_VERSION,
        prompt_version=PROMPT_VERSION,
    )


def analyze_script_mock(
    show_title: str,
    episode_title: Optional[str] = None,
) -> ScriptAnalysis:
    """Generate a mock analysis for testing without API calls."""
    import random

    scores = []
    for name in get_factor_names():
        scores.append(FactorScore(
            factor_name=name,
            score=random.randint(3, 9),
            confidence=round(random.uniform(0.5, 1.0), 2),
            evidence=f"[Mock evidence for {name}]",
            notes="",
        ))

    return ScriptAnalysis(
        show_title=show_title,
        episode_title=episode_title,
        script_filename="mock",
        factor_scores=scores,
        analysis_version=ANALYSIS_VERSION,
        prompt_version=f"{PROMPT_VERSION}-mock",
    )


# ---------------------------------------------------------------------------
# Batch analysis
# ---------------------------------------------------------------------------

def analyze_batch(
    records: list[LinkedRecord],
    output_dir: str = "output/analyses",
    use_mock: bool = False,
    api_key: Optional[str] = None,
    model: str = "claude-sonnet-4-20250514",
    delay_between: float = 1.0,
) -> list[ScriptAnalysis]:
    """Run analysis on all linked records that have scripts."""
    os.makedirs(output_dir, exist_ok=True)
    results: list[ScriptAnalysis] = []
    total = sum(1 for r in records if r.scripts)

    print(f"\nAnalyzing {total} shows with scripts...")
    if use_mock:
        print("  (Using mock analysis — no API calls)")

    for i, record in enumerate(records):
        if not record.scripts:
            continue

        show = record.show.title
        # Use first script for analysis (or combine if multiple)
        script = record.scripts[0]

        print(f"  [{i + 1}/{total}] {show}...", end=" ", flush=True)

        # Check for cached result
        cache_path = os.path.join(output_dir, f"{_safe_filename(show)}.json")
        if os.path.exists(cache_path):
            print("(cached)")
            with open(cache_path) as f:
                results.append(ScriptAnalysis(**json.load(f)))
            continue

        try:
            if use_mock:
                analysis = analyze_script_mock(show, script.episode_title)
            else:
                analysis = analyze_script_with_claude(
                    script.text, show, script.episode_title,
                    api_key=api_key, model=model,
                )
            analysis.script_filename = script.filename

            # Cache result
            with open(cache_path, "w") as f:
                json.dump(analysis.model_dump(), f, indent=2)

            results.append(analysis)
            print("done")

            if not use_mock and delay_between > 0:
                time.sleep(delay_between)

        except Exception as e:
            print(f"ERROR: {e}")
            continue

    print(f"\n✓ Completed {len(results)}/{total} analyses")
    return results


def load_analyses(directory: str = "output/analyses") -> list[ScriptAnalysis]:
    """Load all cached analysis results."""
    results = []
    d = Path(directory)
    if not d.exists():
        return results
    for path in sorted(d.glob("*.json")):
        with open(path) as f:
            results.append(ScriptAnalysis(**json.load(f)))
    return results


def _safe_filename(title: str) -> str:
    """Convert a title to a safe filename."""
    import re
    safe = re.sub(r"[^a-zA-Z0-9\s-]", "", title)
    safe = re.sub(r"\s+", "_", safe).strip("_")
    return safe.lower()[:80]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    from ingest import load_linked_dataset

    dataset_path = sys.argv[1] if len(sys.argv) > 1 else "data/linked_dataset.json"
    use_mock = "--mock" in sys.argv

    records = load_linked_dataset(dataset_path)
    # Reload scripts for text content
    from ingest import load_scripts
    scripts_dir = sys.argv[2] if len(sys.argv) > 2 else "data/scripts"
    scripts = load_scripts(scripts_dir)

    # Re-attach script text to records
    script_map = {s.filename: s for s in scripts}
    for record in records:
        for i, rs in enumerate(record.scripts):
            if rs.filename in script_map:
                record.scripts[i] = script_map[rs.filename]

    results = analyze_batch(records, use_mock=use_mock)
    print(f"\nResults saved to output/analyses/")
