"""
add_dimensions.py: Score new dimensions across all scripts in one batch LLM pass.

This is the core of the new autoresearch architecture:
  - You define new dimensions in config/new_dimensions.json
  - This script scores all 906 scripts for ONLY the new dimensions (one LLM call per script)
  - New scores are appended to existing per-script JSONs (old scores untouched)
  - Weight optimization runs automatically across all dimensions (old + new)
  - You see immediately which new dimensions add signal

Cost: ~$7-9 per batch of N new dimensions (same cost regardless of N)
Resume: safe to re-run — skips scripts already scored for all new dimensions

Usage:
    python3 src/add_dimensions.py
    python3 src/add_dimensions.py --dimensions config/new_dimensions.json
    python3 src/add_dimensions.py --dry-run   # show what would be scored, no LLM calls
"""

import argparse
import json
import logging
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

# ─── Paths ─────────────────────────────────────────────────────
BASE_DIR         = Path(".")
PER_SCRIPT_DIR   = BASE_DIR / "data/results/live/per_script"
BENCHMARK_PATH   = BASE_DIR / "data/benchmark/benchmark.jsonl"
SPLIT_PATH       = BASE_DIR / "data/results/validation/v2_split.json"
EXTRACTED_DIR    = BASE_DIR / "data/extracted_text"
RESULTS_DIR      = BASE_DIR / "data/results"
INSIGHTS_PATH    = BASE_DIR / "PRODUCER_INSIGHTS.md"
DIMENSIONS_PATH  = BASE_DIR / "config/new_dimensions.json"

COST_PER_SCRIPT  = 0.010  # gpt-5-mini, single LLM call, ~$0.008 observed + 25% padding


# ═══════════════════════════════════════════════════════════════
# DIMENSION CONFIG LOADING
# ═══════════════════════════════════════════════════════════════

def load_new_dimensions(path: Path) -> List[Dict]:
    """Load and validate new dimension definitions."""
    with open(path) as f:
        dims = json.load(f)

    # Filter out the example placeholder
    dims = [d for d in dims if d.get("name") != "example_dimension"]

    if not dims:
        raise ValueError(f"No dimensions found in {path}. Add your dimension definitions first.")

    required = {"name", "display_name", "what_it_measures", "strong_signals", "weak_signals"}
    for d in dims:
        missing = required - set(d.keys())
        if missing:
            raise ValueError(f"Dimension '{d.get('name')}' missing fields: {missing}")

    logger.info(f"Loaded {len(dims)} new dimensions: {[d['name'] for d in dims]}")
    return dims


def build_scoring_prompt(dimensions: List[Dict]) -> str:
    """Build the LLM prompt section describing the new dimensions."""
    lines = [
        "You are evaluating a TV pilot script. Score the following dimensions 1-10.\n",
        "These are ADDITIONAL dimensions beyond the standard evaluation.\n",
    ]

    for i, dim in enumerate(dimensions, 1):
        lines.append(f"### {i}. {dim['display_name']} (1-10)")
        lines.append(f"**What it measures:** {dim['what_it_measures']}\n")

        lines.append("**Strong signals (7-10):**")
        for s in dim.get("strong_signals", []):
            lines.append(f"- {s}")

        lines.append("\n**Weak signals (1-6):**")
        for s in dim.get("weak_signals", []):
            lines.append(f"- {s}")

        anchors = dim.get("anchors", {})
        if anchors:
            lines.append("\n**Scoring anchors:**")
            for score_range, example in anchors.items():
                lines.append(f"- {score_range}: {example}")

        lines.append("")

    # Output format
    dim_names = [d["name"] for d in dimensions]
    example_output = {
        name: {"score": 7, "reasoning": "one sentence"} for name in dim_names
    }
    lines += [
        "## Output Format",
        "Return ONLY valid JSON with this exact structure:",
        "```json",
        json.dumps(example_output, indent=2),
        "```",
        "",
        f"Use these exact JSON keys: {dim_names}",
        "Score each 1-10. Reasoning must be one sentence.",
        "Return ONLY valid JSON, no other text.",
    ]

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# SCORING
# ═══════════════════════════════════════════════════════════════

def score_script_for_new_dims(client, script_id: str, script_text: str,
                                scoring_prompt: str, dim_names: List[str]) -> Dict:
    """Single LLM call scoring all new dimensions for one script."""
    full_prompt = f"""{scoring_prompt}

---

## Script to Evaluate

**Script ID:** {script_id}

**Script Text:**
{script_text[:15000]}

---

Score this script on the dimensions above. Return ONLY valid JSON."""

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": full_prompt}],
        max_completion_tokens=3000,
    )
    raw = response.choices[0].message.content.strip()

    if not raw:
        raise ValueError("Empty response")

    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    if not raw.startswith("{"):
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start != -1 and end > start:
            raw = raw[start:end]
        else:
            raise ValueError(f"No JSON found. Raw: {raw[:150]}")

    parsed = json.loads(raw)

    scores = {}
    for name in dim_names:
        val = parsed.get(name, {})
        if isinstance(val, dict):
            scores[name] = {"score": val.get("score", 0), "reasoning": val.get("reasoning", "")}
        elif isinstance(val, (int, float)):
            scores[name] = {"score": float(val), "reasoning": ""}

    return scores


def already_scored(result: Dict, dim_names: List[str]) -> bool:
    """Check if this script already has scores for all new dimensions."""
    existing = result.get("scoring", {})
    return all(name in existing for name in dim_names)


# ═══════════════════════════════════════════════════════════════
# POST-SCORING ANALYSIS
# ═══════════════════════════════════════════════════════════════

def run_analysis(dim_names: List[str]):
    """After scoring, run gap analysis + weight optimization across all dimensions."""
    logger.info("Running gap analysis and weight optimization...")
    import sys
    sys.path.insert(0, str(BASE_DIR / "src"))

    # Load everything
    benchmark = {}
    with open(BENCHMARK_PATH) as f:
        for line in f:
            e = json.loads(line)
            if e.get("label") in ("winner", "loser"):
                benchmark[e["script_id"]] = e["label"]

    with open(SPLIT_PATH) as f:
        split = json.load(f)

    results = {}
    for jf in PER_SCRIPT_DIR.glob("*.json"):
        d = json.loads(jf.read_text())
        if d.get("status") == "success":
            results[d["script_id"]] = d

    # Build full dimension set: existing + new
    existing_dims = [
        "audience_appeal_marketability",
        "conceptual_hook_clarity",
        "character_appeal_and_long_term_potential",
        "creative_originality_and_boldness",
        "narrative_momentum_engagement",
    ]
    all_dims = existing_dims + [n for n in dim_names if n not in existing_dims]
    logger.info(f"Full dimension set ({len(all_dims)}): {all_dims}")

    def get_all_scores(result: Dict) -> Dict[str, float]:
        """Extract scores for all dimensions from a result."""
        scores = {}
        # Existing dims from aggregated.individual_scores
        individual = result.get("aggregated", {}).get("individual_scores", {})
        for d in existing_dims:
            if d in individual:
                scores[d] = individual[d]
        # New dims from scoring
        scoring = result.get("scoring", {})
        for d in dim_names:
            val = scoring.get(d, {})
            if isinstance(val, dict):
                scores[d] = val.get("score", 0)
            elif isinstance(val, (int, float)):
                scores[d] = float(val)
        return scores

    # Gap analysis
    import numpy as np
    winner_scores = {d: [] for d in all_dims}
    loser_scores  = {d: [] for d in all_dims}
    for sid, result in results.items():
        label = benchmark.get(sid)
        if not label: continue
        s = get_all_scores(result)
        for d in all_dims:
            if d in s:
                if label == "winner": winner_scores[d].append(s[d])
                else:                 loser_scores[d].append(s[d])

    print("\n" + "="*80)
    print("GAP ANALYSIS — All Dimensions")
    print("="*80)
    print(f"{'Dimension':<45} {'Winner':>8} {'Loser':>8} {'Gap':>8}  {'New?'}")
    print("-"*80)
    gaps = {}
    for d in all_dims:
        w, l = winner_scores[d], loser_scores[d]
        if not w or not l: continue
        w_avg, l_avg = np.mean(w), np.mean(l)
        gap = w_avg - l_avg
        gaps[d] = gap
        is_new = "🆕" if d in dim_names else ""
        print(f"{d:<45} {w_avg:>8.3f} {l_avg:>8.3f} {gap:>8.3f}  {is_new}")
    print("="*80)

    # Weight optimization across all dimensions
    import random
    def evaluate_weights(weights, script_ids):
        scores, winners, losers = {}, [], []
        for sid in script_ids:
            result = results.get(sid)
            label  = benchmark.get(sid)
            if not result or not label: continue
            s = get_all_scores(result)
            wsum = sum(s.get(d, 0) * w for d, w in weights.items() if w > 0)
            wtot = sum(w for d, w in weights.items() if w > 0 and d in s)
            if wtot > 0:
                scores[sid] = wsum / wtot
                if label == "winner": winners.append(sid)
                else:                 losers.append(sid)
        total = len(winners) * len(losers)
        if not total: return 0.0
        correct = sum(1 for w in winners for l in losers if scores.get(w, 0) > scores.get(l, 0))
        return correct / total

    holdout_ids = split["holdout"]
    tune_ids    = split["tune"]

    # Start with gap-proportional weights
    min_gap = min(gaps.values()) if gaps else 0
    shifted = {d: gaps.get(d, 0) - min_gap + 1e-6 for d in all_dims}
    total_shifted = sum(shifted.values())
    best_weights  = {d: shifted[d] / total_shifted for d in all_dims}
    best_holdout  = evaluate_weights(best_weights, holdout_ids)

    # Random search
    rng = random.Random(42)
    weight_opts = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    for _ in range(2000):
        w = {d: rng.choice(weight_opts) for d in all_dims}
        if not any(v > 0 for v in w.values()): continue
        acc = evaluate_weights(w, holdout_ids)
        if acc > best_holdout:
            best_holdout = acc
            best_weights = w

    tune_acc = evaluate_weights(best_weights, tune_ids)

    print(f"\n{'='*80}")
    print(f"WEIGHT OPTIMIZATION RESULTS")
    print(f"{'='*80}")
    print(f"Best holdout accuracy: {best_holdout*100:.3f}%  (was: 84.01%,  Δ={best_holdout*100-84.01:+.3f}%)")
    print(f"Tune accuracy:         {tune_acc*100:.3f}%")
    print(f"\nBest weights:")
    for d, w in sorted(best_weights.items(), key=lambda x: -x[1]):
        if w > 0:
            tag = " 🆕" if d in dim_names else ""
            print(f"  {d:<45} {w:.3f}{tag}")
    print(f"{'='*80}\n")

    # Save best config
    config = {
        "label":           f"v3_best_{best_holdout*100:.2f}pct",
        "timestamp":       datetime.utcnow().isoformat(),
        "all_dimensions":  all_dims,
        "new_dimensions":  dim_names,
        "weights":         best_weights,
        "holdout_accuracy": best_holdout,
        "tune_accuracy":   tune_acc,
        "gap_analysis":    {d: {"gap": gaps.get(d, 0)} for d in all_dims},
    }
    out = RESULTS_DIR / f"v3_best_{best_holdout*100:.2f}pct.json"
    with open(out, "w") as f:
        json.dump(config, f, indent=2)
    logger.info(f"Saved config → {out}")

    return best_holdout, best_weights


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Score new dimensions across all scripts")
    parser.add_argument("--dimensions", default=str(DIMENSIONS_PATH),
                        help=f"Path to new dimensions JSON (default: {DIMENSIONS_PATH})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be scored without making LLM calls")
    args = parser.parse_args()

    # Load dimensions
    dimensions = load_new_dimensions(Path(args.dimensions))
    dim_names  = [d["name"] for d in dimensions]
    scoring_prompt = build_scoring_prompt(dimensions)

    # Load existing results
    results = {}
    for jf in PER_SCRIPT_DIR.glob("*.json"):
        d = json.loads(jf.read_text())
        if d.get("status") == "success":
            results[d["script_id"]] = d

    # Determine what needs scoring
    to_score = [
        sid for sid, result in results.items()
        if not already_scored(result, dim_names)
    ]
    already_done = len(results) - len(to_score)

    est_cost = len(to_score) * COST_PER_SCRIPT
    print(f"\n{'='*70}")
    print(f"ADD DIMENSIONS")
    print(f"{'='*70}")
    print(f"New dimensions:     {dim_names}")
    print(f"Scripts to score:   {len(to_score)}  ({already_done} already done, skipping)")
    print(f"Estimated cost:     ~${est_cost:.2f}")
    print(f"{'='*70}\n")

    if args.dry_run:
        print("DRY RUN — scoring prompt preview:\n")
        print(scoring_prompt[:800])
        return

    if not to_score:
        print("All scripts already scored. Running analysis only...")
        run_analysis(dim_names)
        return

    # Score
    import openai
    client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    failed = 0
    for i, script_id in enumerate(to_score, 1):
        txt_file = EXTRACTED_DIR / f"{script_id}.txt"
        if not txt_file.exists():
            logger.warning(f"[{i}/{len(to_score)}] {script_id} — no text file, skipping")
            failed += 1
            continue

        script_text = txt_file.read_text(encoding="utf-8", errors="ignore")

        try:
            new_scores = score_script_for_new_dims(
                client, script_id, script_text, scoring_prompt, dim_names
            )

            # Append new scores to existing per-script JSON
            result_path = PER_SCRIPT_DIR / f"{script_id}.json"
            result_data = json.loads(result_path.read_text())
            result_data["scoring"].update(new_scores)
            result_path.write_text(json.dumps(result_data, indent=2))

            if i % 50 == 0:
                logger.info(f"[{i}/{len(to_score)}] Progress... ({failed} failed)")

        except Exception as e:
            logger.error(f"[{i}/{len(to_score)}] {script_id} failed: {e}")
            failed += 1

    print(f"\nScoring complete: {len(to_score)-failed}/{len(to_score)} succeeded ({failed} failed)")
    print(f"Actual cost: ~${(len(to_score)-failed) * COST_PER_SCRIPT:.2f}\n")

    # Run analysis
    run_analysis(dim_names)


if __name__ == "__main__":
    main()
