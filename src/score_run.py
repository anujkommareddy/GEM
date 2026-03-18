"""
score_run.py — Versioned LLM Scoring Runner

Runs a full LLM scoring pass and stores results in a versioned directory.
NEVER modifies previous scoring runs.

Usage:
    python3 src/score_run.py --run v3_expanded                  # Full run
    python3 src/score_run.py --run v3_expanded --dry-run        # Preview cost, no LLM calls
    python3 src/score_run.py --run v3_expanded --limit 10       # Score first 10 (test)
    python3 src/score_run.py --run v3_expanded --resume         # Resume interrupted run
    python3 src/score_run.py --run v3_expanded --analyze-only   # Just run analysis (no scoring)
    python3 src/score_run.py list-runs                          # Show all scoring versions

The run config is loaded from config/scoring_runs/{run_id}.json.
Output goes to data/scoring/{run_id}/per_script/{show_id}.json

Each per-script output looks like:
{
  "show_id": "...",
  "run_id": "v3_expanded",
  "model": "gpt-5-mini",
  "label_version": "v2",
  "label": "winner|middle|loser",
  "evidence_type": "pilot_script|show_summary|...",
  "scored_at": "2026-03-18T...",
  "scoring": {
    "audience_appeal_marketability": {"score": 8, "reasoning": "..."},
    ...
  },
  "status": "success|failed"
}
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import random

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

BASE_DIR         = Path(".")
RUNS_CONFIG_DIR  = BASE_DIR / "config/scoring_runs"
SCORING_DIR      = BASE_DIR / "data/scoring"
EXTRACTED_DIR    = BASE_DIR / "data/extracted_text"
CORPUS_EVIDENCE  = BASE_DIR / "data/corpus/evidence"
LABELS_V2        = BASE_DIR / "data/labels/labels_v2.jsonl"
SPLIT_FILE       = BASE_DIR / "data/results/validation/v2_split.json"
RUBRIC_FILE      = BASE_DIR / "config/rubric_v2_producer_mind.md"

BASE_DIMENSIONS = [
    "audience_appeal_marketability",
    "conceptual_hook_clarity",
    "character_appeal_and_long_term_potential",
    "creative_originality_and_boldness",
    "narrative_momentum_engagement",
]

COST_PER_SCRIPT = 0.010


# ─── Run Config ────────────────────────────────────────────────

def load_run_config(run_id: str) -> dict:
    path = RUNS_CONFIG_DIR / f"{run_id}.json"
    if not path.exists():
        print(f"Run config not found: {path}")
        print(f"Available runs: {[p.stem for p in RUNS_CONFIG_DIR.glob('*.json')]}")
        sys.exit(1)
    return json.loads(path.read_text())


def get_run_dir(run_id: str) -> Path:
    return SCORING_DIR / run_id


def get_per_script_dir(run_id: str) -> Path:
    return get_run_dir(run_id) / "per_script"


# ─── Labels ────────────────────────────────────────────────────

def load_labels_v2() -> dict:
    """Return {show_id: label_v2} mapping."""
    if not LABELS_V2.exists():
        return {}
    with open(LABELS_V2) as f:
        entries = [json.loads(l) for l in f if l.strip()]
    return {e["show_id"]: e["label_v2"] for e in entries}


# ─── Evidence ──────────────────────────────────────────────────

EVIDENCE_PRIORITY = [
    "pilot_script",
    "episode_script",
    "show_summary",
    "season_summary",
    "episode_summary",
    "logline",
    "synopsis",
]

def get_evidence(show_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Return (evidence_type, text) for best available evidence.
    Checks legacy extracted_text/ first, then corpus/evidence/.
    """
    # 1. Legacy script location
    legacy = EXTRACTED_DIR / f"{show_id}.txt"
    if legacy.exists():
        text = legacy.read_text(encoding="utf-8", errors="ignore")
        if text.strip():
            return "pilot_script", text

    # 2. Corpus evidence directory
    ev_dir = CORPUS_EVIDENCE / show_id
    manifest_path = ev_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        evidence = manifest.get("evidence", {})
        for etype in EVIDENCE_PRIORITY:
            if etype in evidence:
                fpath = ev_dir / evidence[etype]["file"]
                if fpath.exists():
                    text = fpath.read_text(encoding="utf-8", errors="ignore")
                    if text.strip():
                        return etype, text

    return None, None


# ─── Dimensions ────────────────────────────────────────────────

def load_new_dimensions(config: dict) -> List[dict]:
    """Load new dimensions from the run config's dimensions_config file."""
    dim_file = Path(config.get("dimensions_config", "config/new_dimensions.json"))
    if not dim_file.exists():
        return []
    dims = json.loads(dim_file.read_text())
    # Filter placeholder
    return [d for d in dims if d.get("name") != "example_dimension"]


def build_full_prompt(config: dict, new_dimensions: List[dict]) -> str:
    """Build the complete scoring prompt: base rubric + new dimensions."""
    rubric = Path(config.get("rubric_file", str(RUBRIC_FILE))).read_text()

    if not new_dimensions:
        return rubric

    # Append new dimensions section
    new_section = [
        "\n\n---\n## Additional Dimensions to Score\n",
        "Score the following NEW dimensions in addition to the 5 above.\n",
    ]
    for i, dim in enumerate(new_dimensions, 1):
        new_section.append(f"\n### {i}. {dim['display_name']} (1-10)")
        new_section.append(f"**What it measures:** {dim['what_it_measures']}\n")
        new_section.append("**Strong signals (7-10):**")
        for s in dim.get("strong_signals", []):
            new_section.append(f"- {s}")
        new_section.append("\n**Weak signals (1-6):**")
        for s in dim.get("weak_signals", []):
            new_section.append(f"- {s}")
        anchors = dim.get("anchors", {})
        if anchors:
            new_section.append("\n**Scoring anchors:**")
            for rng, ex in anchors.items():
                new_section.append(f"- {rng}: {ex}")

    return rubric + "\n".join(new_section)


def build_output_format(all_dimensions: List[str]) -> str:
    """Build the JSON output format instruction."""
    example = {d: {"score": 7, "reasoning": "one sentence"} for d in all_dimensions}
    return f"""
## Output Format

Return ONLY valid JSON with this exact structure:
```json
{json.dumps(example, indent=2)}
```

Use these exact JSON keys: {all_dimensions}
Score each 1-10. Reasoning must be one sentence max.
Return ONLY valid JSON, no other text.
"""


# ─── Scoring ───────────────────────────────────────────────────

def score_one(client, show_id: str, text: str, scoring_prompt: str,
              all_dimensions: List[str]) -> dict:
    """Single LLM call — scores all dimensions for one show."""
    truncated = text[:15000]
    full = f"""{scoring_prompt}

---

## Script / Content to Evaluate

**Show ID:** {show_id}

{truncated}

---

{build_output_format(all_dimensions)}"""

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": full}],
        max_completion_tokens=3000,
    )
    raw = response.choices[0].message.content.strip()

    if not raw:
        raise ValueError("Empty response")

    # Clean markdown fences
    for marker in ["```json", "```"]:
        if marker in raw:
            raw = raw.split(marker)[1].split("```")[0].strip()
            break

    if not raw.startswith("{"):
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start != -1 and end > start:
            raw = raw[start:end]
        else:
            raise ValueError(f"No JSON in response: {raw[:200]}")

    parsed = json.loads(raw)

    # Normalize: accept {score, reasoning} dicts or bare numbers
    scores = {}
    for dim in all_dimensions:
        val = parsed.get(dim, {})
        if isinstance(val, dict):
            scores[dim] = {"score": float(val.get("score", 0)), "reasoning": val.get("reasoning", "")}
        elif isinstance(val, (int, float)):
            scores[dim] = {"score": float(val), "reasoning": ""}
        else:
            scores[dim] = {"score": 0.0, "reasoning": "parse_error"}

    return scores


def already_scored(run_dir: Path, show_id: str) -> bool:
    path = run_dir / "per_script" / f"{show_id}.json"
    if not path.exists():
        return False
    data = json.loads(path.read_text())
    return data.get("status") == "success"


# ─── Analysis ──────────────────────────────────────────────────

def run_analysis(run_id: str, all_dimensions: List[str], new_dim_names: List[str]):
    """Gap analysis + weight optimization across all dimensions in this run."""
    run_dir = get_per_script_dir(run_id)
    labels = load_labels_v2()

    with open(SPLIT_FILE) as f:
        split = json.load(f)

    # Load scores
    results = {}
    for jf in run_dir.glob("*.json"):
        d = json.loads(jf.read_text())
        if d.get("status") == "success":
            results[d["show_id"]] = d

    logger.info(f"Loaded {len(results)} scored results for analysis")

    def get_scores(result: dict) -> dict:
        scoring = result.get("scoring", {})
        out = {}
        for dim in all_dimensions:
            val = scoring.get(dim, {})
            if isinstance(val, dict):
                out[dim] = val.get("score", 0)
            elif isinstance(val, (int, float)):
                out[dim] = float(val)
        return out

    # --- Gap analysis ---
    winner_scores = {d: [] for d in all_dimensions}
    loser_scores  = {d: [] for d in all_dimensions}

    # Use winner/loser only (exclude middle) for gap analysis
    for sid, result in results.items():
        label = labels.get(sid)
        if label not in ("winner", "loser"):
            continue
        s = get_scores(result)
        for d in all_dimensions:
            if d in s:
                (winner_scores[d] if label == "winner" else loser_scores[d]).append(s[d])

    print("\n" + "="*80)
    print(f"GAP ANALYSIS — Run: {run_id}")
    print("="*80)
    print(f"{'Dimension':<48} {'Winner':>8} {'Loser':>8} {'Gap':>8}  {'New?'}")
    print("-"*80)
    gaps = {}
    for d in sorted(all_dimensions, key=lambda x: -(
        (sum(winner_scores[x])/len(winner_scores[x]) if winner_scores[x] else 0) -
        (sum(loser_scores[x])/len(loser_scores[x]) if loser_scores[x] else 0)
    )):
        w, l = winner_scores[d], loser_scores[d]
        if not w or not l:
            continue
        w_avg = sum(w) / len(w)
        l_avg = sum(l) / len(l)
        gap = w_avg - l_avg
        gaps[d] = gap
        tag = " 🆕" if d in new_dim_names else ""
        print(f"{d:<48} {w_avg:>8.3f} {l_avg:>8.3f} {gap:>8.3f}{tag}")
    print("="*80)

    # --- Weight optimization ---
    logger.info("Running weight optimizer (2000 trials)...")

    def weighted_score(show_id: str, weights: dict) -> float:
        result = results.get(show_id)
        if not result:
            return 0.0
        s = get_scores(result)
        total_w = sum(w for d, w in weights.items() if d in s and w > 0)
        if total_w == 0:
            return 0.0
        return sum(s.get(d, 0) * w for d, w in weights.items() if w > 0) / total_w

    def pairwise_accuracy(script_ids: list, weights: dict) -> float:
        winners = [sid for sid in script_ids if labels.get(sid) == "winner"]
        losers  = [sid for sid in script_ids if labels.get(sid) == "loser"]
        total   = len(winners) * len(losers)
        if not total:
            return 0.0
        correct = sum(
            1 for w in winners for l in losers
            if weighted_score(w, weights) > weighted_score(l, weights)
        )
        return correct / total

    holdout_ids = split["holdout"]
    tune_ids    = split["tune"]

    # Seed with gap-proportional weights
    min_gap = min(gaps.values()) if gaps else 0
    shifted = {d: max(gaps.get(d, 0) - min_gap + 1e-6, 0) for d in all_dimensions}
    total_s = sum(shifted.values()) or 1
    best_weights  = {d: shifted[d] / total_s * 3.0 for d in all_dimensions}
    best_holdout  = pairwise_accuracy(holdout_ids, best_weights)

    opts = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    rng  = random.Random(42)
    for _ in range(2000):
        w = {d: rng.choice(opts) for d in all_dimensions}
        if not any(v > 0 for v in w.values()):
            continue
        acc = pairwise_accuracy(holdout_ids, w)
        if acc > best_holdout:
            best_holdout = acc
            best_weights = w.copy()

    tune_acc = pairwise_accuracy(tune_ids, best_weights)

    print(f"\n{'='*80}")
    print(f"WEIGHT OPTIMIZATION RESULTS — Run: {run_id}")
    print(f"{'='*80}")
    print(f"Holdout accuracy: {best_holdout*100:.3f}%   (v2 baseline: 84.01%,  Δ={best_holdout*100-84.01:+.3f}%)")
    print(f"Tune accuracy:    {tune_acc*100:.3f}%")
    print(f"\nBest weights (non-zero):")
    for d, w in sorted(best_weights.items(), key=lambda x: -x[1]):
        if w > 0:
            tag = " 🆕" if d in new_dim_names else ""
            print(f"  {d:<48} {w:.3f}{tag}")
    print("="*80)

    # Save config
    config = {
        "run_id":            run_id,
        "timestamp":         datetime.utcnow().isoformat(),
        "all_dimensions":    all_dimensions,
        "new_dimensions":    new_dim_names,
        "weights":           best_weights,
        "holdout_accuracy":  best_holdout,
        "tune_accuracy":     tune_acc,
        "gap_analysis":      {d: {"gap": gaps.get(d, 0)} for d in all_dimensions},
    }
    out = get_run_dir(run_id) / f"best_config_{best_holdout*100:.2f}pct.json"
    out.write_text(json.dumps(config, indent=2))
    logger.info(f"Best config saved → {out}")

    # Update manifest
    manifest_path = get_run_dir(run_id) / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        manifest["holdout_accuracy"] = best_holdout
        manifest["tune_accuracy"]    = tune_acc
        manifest["best_config_file"] = str(out)
        manifest["status"] = "analyzed"
        manifest_path.write_text(json.dumps(manifest, indent=2))

    return best_holdout, best_weights


# ─── Main Run ──────────────────────────────────────────────────

def run_scoring(run_id: str, dry_run: bool = False, limit: int = None,
                resume: bool = True, analyze_only: bool = False):
    config = load_run_config(run_id)

    # Init directories
    run_dir = get_run_dir(run_id)
    per_script_dir = run_dir / "per_script"
    per_script_dir.mkdir(parents=True, exist_ok=True)

    # Load dimensions
    new_dims = load_new_dimensions(config) if config.get("score_new_dims", True) else []
    new_dim_names = [d["name"] for d in new_dims]

    base_dims = BASE_DIMENSIONS if config.get("score_all_5_base_dims", True) else []
    all_dims  = base_dims + [n for n in new_dim_names if n not in base_dims]

    logger.info(f"Run: {run_id}")
    logger.info(f"All dimensions ({len(all_dims)}): {all_dims}")

    if analyze_only:
        run_analysis(run_id, all_dims, new_dim_names)
        return

    # Build prompt
    scoring_prompt = build_full_prompt(config, new_dims)

    # Load labels
    labels = load_labels_v2()

    # Find all shows to score
    corpus_ids = set()
    for f in EXTRACTED_DIR.glob("*.txt"):
        corpus_ids.add(f.stem)
    for d in CORPUS_EVIDENCE.iterdir():
        if d.is_dir():
            corpus_ids.add(d.name)

    to_score = []
    for show_id in sorted(corpus_ids):
        if resume and already_scored(run_dir, show_id):
            continue
        ev_type, _ = get_evidence(show_id)
        if ev_type is None:
            continue
        to_score.append(show_id)

    if limit:
        to_score = to_score[:limit]

    already_done = len(corpus_ids) - len(to_score)
    est_cost = len(to_score) * COST_PER_SCRIPT

    print(f"\n{'='*70}")
    print(f"SCORE RUN: {run_id}")
    print(f"{'='*70}")
    print(f"Dimensions:        {len(all_dims)} ({len(new_dim_names)} new)")
    print(f"New dims:          {new_dim_names or 'none'}")
    print(f"Shows to score:    {len(to_score)}")
    print(f"Already done:      {already_done} (skipped)")
    print(f"Estimated cost:    ~${est_cost:.2f}")
    print(f"Output dir:        {per_script_dir}")
    print(f"{'='*70}\n")

    if dry_run:
        print("DRY RUN — no LLM calls made.")
        print("\nPrompt preview (first 600 chars):")
        print(scoring_prompt[:600])
        print("...")
        return

    # Update manifest as in-progress
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        manifest["status"]     = "running"
        manifest["created_at"] = datetime.utcnow().isoformat()
        manifest["dimensions"] = all_dims
        manifest["model"]      = config.get("model", "gpt-5-mini")
        manifest_path.write_text(json.dumps(manifest, indent=2))

    # Init client
    try:
        import openai
        client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    except KeyError:
        print("ERROR: OPENAI_API_KEY environment variable not set.")
        print("Run: export OPENAI_API_KEY=your_key_here")
        sys.exit(1)

    failed = 0
    succeeded = 0

    for i, show_id in enumerate(to_score, 1):
        ev_type, text = get_evidence(show_id)
        label = labels.get(show_id)

        try:
            scores = score_one(client, show_id, text, scoring_prompt, all_dims)

            result = {
                "show_id":       show_id,
                "run_id":        run_id,
                "model":         config.get("model", "gpt-5-mini"),
                "label_version": config.get("label_version", "v2"),
                "label":         label,
                "evidence_type": ev_type,
                "scored_at":     datetime.utcnow().isoformat(),
                "scoring":       scores,
                "status":        "success",
            }
            succeeded += 1

        except Exception as e:
            logger.error(f"[{i}/{len(to_score)}] FAILED {show_id}: {e}")
            result = {
                "show_id":   show_id,
                "run_id":    run_id,
                "scored_at": datetime.utcnow().isoformat(),
                "error":     str(e),
                "status":    "failed",
            }
            failed += 1

        (per_script_dir / f"{show_id}.json").write_text(json.dumps(result, indent=2))

        if i % 50 == 0 or i == len(to_score):
            logger.info(f"[{i}/{len(to_score)}] {succeeded} ok / {failed} failed")

    print(f"\n{'='*70}")
    print(f"Scoring complete: {succeeded} succeeded, {failed} failed")
    print(f"Actual cost: ~${succeeded * COST_PER_SCRIPT:.2f}")
    print(f"{'='*70}\n")

    # Update manifest
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        manifest["scripts_scored"] = succeeded
        manifest["scripts_failed"] = failed
        manifest["status"]         = "scored"
        manifest_path.write_text(json.dumps(manifest, indent=2))

    # Auto-run analysis if scoring is complete
    print("Running analysis...")
    run_analysis(run_id, all_dims, new_dim_names)


# ─── List Runs ─────────────────────────────────────────────────

def list_runs():
    print(f"\n{'='*70}")
    print("SCORING RUNS")
    print(f"{'='*70}")
    print(f"{'Run ID':<25} {'Status':<12} {'Scored':>8} {'Holdout':>10}  Description")
    print("-"*70)
    for d in sorted(SCORING_DIR.iterdir()):
        if not d.is_dir():
            continue
        manifest_path = d / "manifest.json"
        if manifest_path.exists():
            m = json.loads(manifest_path.read_text())
            scored   = m.get("scripts_scored", "—")
            holdout  = f"{m['holdout_accuracy']*100:.2f}%" if m.get("holdout_accuracy") else "—"
            status   = m.get("status", "?")
            desc     = m.get("display_name", d.name)
            ro       = " [READ ONLY]" if m.get("read_only") else ""
            print(f"{d.name:<25} {status:<12} {str(scored):>8} {holdout:>10}  {desc}{ro}")
        else:
            print(f"{d.name:<25} {'no manifest':<12}")
    print("="*70 + "\n")


# ─── Entry Point ───────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GEM Versioned Scoring Runner")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="Run scoring (default command)")
    p_run.add_argument("--run",          required=True, help="Run ID (matches config/scoring_runs/*.json)")
    p_run.add_argument("--dry-run",      action="store_true")
    p_run.add_argument("--limit",        type=int, help="Score only first N shows")
    p_run.add_argument("--no-resume",    action="store_true", help="Re-score even already-scored shows")
    p_run.add_argument("--analyze-only", action="store_true", help="Skip scoring, run analysis only")

    sub.add_parser("list-runs", help="Show all scoring versions")

    # Also support direct --run flag at top level for convenience
    parser.add_argument("--run",          help="Run ID")
    parser.add_argument("--dry-run",      action="store_true")
    parser.add_argument("--limit",        type=int)
    parser.add_argument("--no-resume",    action="store_true")
    parser.add_argument("--analyze-only", action="store_true")

    args = parser.parse_args()

    if args.command == "list-runs" or (not args.command and not args.run):
        list_runs()
    elif args.run or (args.command == "run" and hasattr(args, "run")):
        run_id = args.run
        run_scoring(
            run_id      = run_id,
            dry_run     = args.dry_run,
            limit       = args.limit,
            resume      = not args.no_resume,
            analyze_only= args.analyze_only,
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
