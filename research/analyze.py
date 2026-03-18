"""Script analysis pipeline.

Runs structured facet analysis on scripts using configurable model providers.
Outputs structured JSON with versioned prompts.
"""

from __future__ import annotations

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

from factors import facets_as_prompt_context, get_default_facets, get_facet_names
from models import FacetScore, FactorScore, LinkedRecord, ScriptAnalysis
from providers import complete, get_cost, DEFAULT_MODELS

PROMPT_VERSION = "v2"
ANALYSIS_VERSION = "v2"

# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert TV script analyst working for a research project studying what makes TV shows succeed or fail.

You will analyze a TV pilot script and score it on 5 specific facets. For each facet, provide:
1. A score from 1-10 (use the full range — 5 is average/neutral)
2. A confidence level from 0.0-1.0 (how confident you are in your assessment)
3. A concise rationale (2-3 sentences of specific evidence from the script)

After scoring all facets, provide a brief overall summary judgment (2-3 sentences).

Be rigorous and honest. Avoid grade inflation. Base your scores ONLY on what's in the script text provided. Do not use knowledge of whether the show succeeded or failed. Analyze the script as if you don't know the outcome."""


def build_analysis_prompt(script_text: str, show_title: str, episode_title: Optional[str] = None) -> str:
    """Build the full analysis prompt for a script."""
    facet_context = facets_as_prompt_context()
    ep_info = f" — Episode: {episode_title}" if episode_title else ""
    facet_names = get_facet_names()

    return f"""Analyze the following TV pilot script for: **{show_title}**{ep_info}

## Facets to Score

{facet_context}

## Script Text

<script>
{script_text}
</script>

## Output Format

Respond with ONLY a JSON object in this exact format:
{{
  "scores": [
    {{
      "facet_name": "{facet_names[0]}",
      "score": 7,
      "confidence": 0.8,
      "rationale": "The pilot establishes a clear multi-quadrant premise..."
    }},
    // ... one entry per facet
  ],
  "summary": "Overall, this pilot..."
}}

Score ALL {len(facet_names)} facets: {', '.join(facet_names)}"""


# ---------------------------------------------------------------------------
# Analysis execution
# ---------------------------------------------------------------------------

class CostTracker:
    """Track API usage costs across a batch run."""

    def __init__(self, budget: float = 100.0):
        self.budget = budget
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0
        self.calls = 0
        self._lock = threading.Lock()

    def record(self, model: str, input_tokens: int, output_tokens: int):
        cost = get_cost(model, input_tokens, output_tokens)
        with self._lock:
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost += cost
            self.calls += 1

    def over_budget(self) -> bool:
        return self.total_cost >= self.budget

    def summary(self) -> str:
        return (f"API calls: {self.calls} | "
                f"Input: {self.total_input_tokens:,} tok | "
                f"Output: {self.total_output_tokens:,} tok | "
                f"Cost: ${self.total_cost:.2f} / ${self.budget:.2f}")


def analyze_script(
    script_text: str,
    show_title: str,
    episode_title: Optional[str] = None,
    provider: str = "openai",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    max_script_chars: int = 150_000,
    cost_tracker: Optional[CostTracker] = None,
) -> ScriptAnalysis:
    """Analyze a single script using the configured provider."""
    model = model or DEFAULT_MODELS.get(provider, "gpt-4o-mini")

    # Truncate very long scripts
    if len(script_text) > max_script_chars:
        script_text = script_text[:max_script_chars] + "\n\n[TRUNCATED — script exceeded character limit]"

    prompt = build_analysis_prompt(script_text, show_title, episode_title)

    result = complete(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=prompt,
        provider=provider,
        model=model,
        api_key=api_key,
    )

    # Track costs
    if cost_tracker:
        cost_tracker.record(result.model, result.input_tokens, result.output_tokens)

    # Parse response
    response_text = result.text
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0].strip()
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0].strip()

    data = json.loads(response_text)

    facet_scores = [FacetScore(**s) for s in data["scores"]]
    summary = data.get("summary", "")

    return ScriptAnalysis(
        show_title=show_title,
        episode_title=episode_title,
        script_filename="",
        facet_scores=facet_scores,
        summary=summary,
        analysis_version=ANALYSIS_VERSION,
        prompt_version=PROMPT_VERSION,
        provider=result.provider,
        model=result.model,
    )


# Keep old name as alias for any external callers
analyze_script_with_claude = analyze_script


def analyze_script_mock(
    show_title: str,
    episode_title: Optional[str] = None,
) -> ScriptAnalysis:
    """Generate a mock analysis for testing without API calls."""
    import random

    scores = []
    for name in get_facet_names():
        scores.append(FacetScore(
            facet_name=name,
            score=random.randint(3, 9),
            confidence=round(random.uniform(0.5, 1.0), 2),
            rationale=f"[Mock rationale for {name}]",
            notes="",
        ))

    return ScriptAnalysis(
        show_title=show_title,
        episode_title=episode_title,
        script_filename="mock",
        facet_scores=scores,
        summary="[Mock summary]",
        analysis_version=ANALYSIS_VERSION,
        prompt_version=f"{PROMPT_VERSION}-mock",
        provider="mock",
        model="mock",
    )


# ---------------------------------------------------------------------------
# Batch analysis
# ---------------------------------------------------------------------------

def _analyze_one(
    show: str,
    script,
    cache_path: str,
    use_mock: bool,
    provider: str,
    model: Optional[str],
    api_key: Optional[str],
    cost_tracker: Optional[CostTracker],
) -> tuple[str, Optional[ScriptAnalysis], Optional[str]]:
    """Analyze a single script. Returns (show, result_or_None, error_or_None)."""
    try:
        if use_mock:
            analysis = analyze_script_mock(show, script.episode_title)
        else:
            analysis = analyze_script(
                script.text, show, script.episode_title,
                provider=provider, model=model, api_key=api_key,
                cost_tracker=cost_tracker,
            )
        analysis.script_filename = script.filename
        with open(cache_path, "w") as f:
            json.dump(analysis.model_dump(), f, indent=2)
        return (show, analysis, None)
    except Exception as e:
        return (show, None, str(e))


def analyze_batch(
    records: list[LinkedRecord],
    output_dir: str = "output/analyses",
    use_mock: bool = False,
    provider: str = "openai",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    budget: float = 100.0,
    max_workers: int = 5,
) -> list[ScriptAnalysis]:
    """Run analysis on all linked records that have scripts (parallel)."""
    model = model or DEFAULT_MODELS.get(provider, "gpt-4o-mini")
    os.makedirs(output_dir, exist_ok=True)
    results: list[ScriptAnalysis] = []
    tracker = CostTracker(budget=budget)

    # Build work list, checking cache first
    work = []
    for record in records:
        if not record.scripts:
            continue
        show = record.show.title
        script = record.scripts[0]
        cache_path = os.path.join(output_dir, f"{_safe_filename(show)}.json")

        if os.path.exists(cache_path):
            try:
                with open(cache_path) as f:
                    cached = ScriptAnalysis(**json.load(f))
                if not use_mock and cached.prompt_version.endswith("-mock"):
                    pass  # Need to re-analyze
                else:
                    results.append(cached)
                    continue
            except Exception:
                pass
        work.append((show, script, cache_path))

    total = len(work) + len(results)
    print(f"\nAnalyzing {total} shows with scripts...")
    print(f"  Provider: {provider} | Model: {model} | Budget: ${budget:.2f} | Workers: {max_workers}")
    print(f"  {len(results)} cached, {len(work)} to analyze")
    if use_mock:
        print("  (Using mock analysis — no API calls)")

    if not work:
        print(f"\n✓ All {total} analyses already cached")
        return results

    done = 0
    errors = 0
    fatal = False
    print_lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for show, script, cache_path in work:
            if not use_mock and tracker.over_budget():
                break
            fut = executor.submit(
                _analyze_one, show, script, cache_path,
                use_mock, provider, model, api_key, tracker,
            )
            futures[fut] = show

        for fut in as_completed(futures):
            show_name, analysis, err = fut.result()
            with print_lock:
                done += 1
                if analysis:
                    results.append(analysis)
                    print(f"  [{done}/{len(work)}] {show_name}... done")
                else:
                    errors += 1
                    print(f"  [{done}/{len(work)}] {show_name}... ERROR: {err[:100] if err else 'unknown'}")
                    if err and ("credit balance" in err or "authentication" in err.lower()):
                        print(f"\n  FATAL: API billing error. Stopping.")
                        fatal = True

                if not use_mock and done % 50 == 0:
                    print(f"    [{tracker.summary()}]")

            if fatal:
                executor.shutdown(wait=False, cancel_futures=True)
                break

    print(f"\n✓ Completed {len(results)}/{total} analyses ({errors} errors)")
    if not use_mock:
        print(f"  {tracker.summary()}")
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
    from ingest import load_scripts
    scripts_dir = sys.argv[2] if len(sys.argv) > 2 else "data/scripts/txt_raw"
    scripts = load_scripts(scripts_dir)

    script_map = {s.filename: s for s in scripts}
    for record in records:
        for i, rs in enumerate(record.scripts):
            if rs.filename in script_map:
                record.scripts[i] = script_map[rs.filename]

    results = analyze_batch(records, use_mock=use_mock)
    print(f"\nResults saved to output/analyses/")
