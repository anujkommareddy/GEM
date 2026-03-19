"""
v3_optimizer.py — Weight Optimizer for v3_expanded Scoring Run

Reads v3 per-script scores (10 dimensions), optimizes dimension weights
to maximize pairwise winner-vs-loser accuracy on the holdout set.

Baseline to beat: 84.01% (v2, 5 dims)

Usage:
    python3 src/v3_optimizer.py                        # Full run, all 10 dims
    python3 src/v3_optimizer.py --dry-run              # Preview data, no optimization
    python3 src/v3_optimizer.py --genre drama          # Genre-stratified run
    python3 src/v3_optimizer.py --genres               # Run all genre strata
    python3 src/v3_optimizer.py --label-audit          # Cross-check labels vs metadata outcomes
    python3 src/v3_optimizer.py --iterations 500       # More iterations (default: 300)

Output:
    data/scoring/v3_expanded/best_weights.json         — best weight config
    data/scoring/v3_expanded/gap_analysis.json         — per-dim winner/loser gaps
    data/scoring/v3_expanded/genre_weights.json        — per-genre weight configs (if --genres)
    data/scoring/v3_expanded/label_audit.json          — label/outcome mismatches (if --label-audit)
"""

import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ─── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR      = Path(".")
V3_DIR        = BASE_DIR / "data/scoring/v3_expanded"
PER_SCRIPT    = V3_DIR / "per_script"
LABELS_FILE   = BASE_DIR / "data/labels/labels_v2.jsonl"
SPLIT_FILE    = BASE_DIR / "data/results/validation/v2_split.json"
METADATA_DIR  = BASE_DIR / "data/metadata"

V2_BASELINE   = 0.8401   # v2 best holdout pairwise accuracy

ALL_DIMS = [
    "audience_appeal_marketability",
    "conceptual_hook_clarity",
    "character_appeal_and_long_term_potential",
    "creative_originality_and_boldness",
    "narrative_momentum_engagement",
    "resonant_originality",
    "world_density_and_texture",
    "tonal_specificity",
    "latent_depth_slow_burn_potential",
    "relationship_density_and_ensemble_engine",
]

BASE_DIMS = ALL_DIMS[:5]
NEW_DIMS  = ALL_DIMS[5:]

# ─── Data Loading ─────────────────────────────────────────────────────────────

def load_scores() -> dict:
    """
    Load all v3 per-script scores.
    Returns {show_id: {dim: score_float, ...}}
    """
    scores = {}
    failed = 0
    for f in PER_SCRIPT.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            if d.get("status") != "success":
                continue
            scoring = d.get("scoring", {})
            flat = {}
            for dim, val in scoring.items():
                if isinstance(val, dict):
                    flat[dim] = float(val.get("score", 0))
                elif isinstance(val, (int, float)):
                    flat[dim] = float(val)
            if flat:
                scores[f.stem] = flat
        except Exception:
            failed += 1
    if failed:
        print(f"  Warning: {failed} score files failed to parse")
    return scores


def load_labels() -> dict:
    """Load labels. Returns {show_id: 'winner'|'loser'|'middle'}"""
    labels = {}
    for line in LABELS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        labels[r["show_id"]] = r["label_v2"]
    return labels


def load_split() -> tuple:
    """Load tune/holdout split. Returns (tune_ids, holdout_ids)."""
    split = json.loads(SPLIT_FILE.read_text())
    return set(split["tune"]), set(split["holdout"])


def load_metadata() -> dict:
    """Load per-show metadata for genre stratification and label audit."""
    meta = {}
    if not METADATA_DIR.exists():
        return meta
    for f in METADATA_DIR.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            d = json.loads(f.read_text())
            meta[d["show_id"]] = d
        except Exception:
            pass
    return meta


# ─── Evaluation ───────────────────────────────────────────────────────────────

def pairwise_accuracy(scores: dict, labels: dict, ids: set,
                      weights: dict, dims: list) -> tuple:
    """
    Compute pairwise accuracy and winner enrichment for a set of show_ids.
    Returns (pairwise_acc_0_to_1, winner_enrichment_pct).
    """
    scored = []
    for sid in ids:
        if sid not in scores or sid not in labels:
            continue
        label = labels[sid]
        if label == "middle":
            continue
        s = scores[sid]
        weighted = sum(s.get(d, 0) * weights.get(d, 0) for d in dims)
        scored.append((weighted, label))

    if not scored:
        return 0.0, 0.0

    winners = [sc for sc, lb in scored if lb == "winner"]
    losers  = [sc for sc, lb in scored if lb == "loser"]

    if not winners or not losers:
        return 0.0, 0.0

    correct = sum(1 for w in winners for l in losers if w > l)
    total   = len(winners) * len(losers)
    pair_acc = correct / total

    # Winner enrichment: % of true winners in top decile
    all_sorted = sorted(scored, key=lambda x: x[0], reverse=True)
    top_n = max(1, len(all_sorted) // 10)
    winners_in_top = sum(1 for _, lb in all_sorted[:top_n] if lb == "winner")
    enrichment = 100.0 * winners_in_top / len(winners)

    return pair_acc, enrichment


# ─── Gap Analysis ─────────────────────────────────────────────────────────────

def compute_gap_analysis(scores: dict, labels: dict, dims: list) -> dict:
    """For each dim, compute winner_avg, loser_avg, and gap."""
    winner_scores = defaultdict(list)
    loser_scores  = defaultdict(list)

    for sid, s in scores.items():
        label = labels.get(sid)
        if label == "winner":
            for d in dims:
                if d in s:
                    winner_scores[d].append(s[d])
        elif label == "loser":
            for d in dims:
                if d in s:
                    loser_scores[d].append(s[d])

    gap_analysis = {}
    for d in dims:
        ws = winner_scores[d]
        ls = loser_scores[d]
        if ws and ls:
            w_avg = sum(ws) / len(ws)
            l_avg = sum(ls) / len(ls)
            gap_analysis[d] = {
                "winner_avg": round(w_avg, 3),
                "loser_avg":  round(l_avg, 3),
                "gap":        round(w_avg - l_avg, 3),
                "winner_n":   len(ws),
                "loser_n":    len(ls),
            }

    return dict(sorted(gap_analysis.items(), key=lambda x: -x[1]["gap"]))


# ─── Optimizer ────────────────────────────────────────────────────────────────

def optimize_weights(scores: dict, labels: dict, tune_ids: set, holdout_ids: set,
                     dims: list, iterations: int = 300,
                     label: str = "global") -> dict:
    """
    Hill-climb weight optimization.
    Phase 1: Gap-proportional seed → fine-tune on tune set.
    Phase 2: Validate best on holdout.
    Returns best config dict.
    """
    # Seed weights proportional to gap
    gap = compute_gap_analysis(scores, labels, dims)
    gaps = {d: max(gap.get(d, {}).get("gap", 0), 0.01) for d in dims}
    total = sum(gaps.values())
    seed_weights = {d: (gaps[d] / total) * len(dims) for d in dims}

    best_weights   = seed_weights.copy()
    best_tune_acc, best_enrichment = pairwise_accuracy(
        scores, labels, tune_ids, best_weights, dims)

    weight_opts = [0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]
    rng = random.Random(42)

    improvements = 0
    for i in range(iterations):
        # Mutation strategy: adjust 1-3 dims
        candidate = best_weights.copy()
        n_mutate = rng.choice([1, 1, 2, 3])
        dims_to_mutate = rng.sample(dims, min(n_mutate, len(dims)))
        for d in dims_to_mutate:
            candidate[d] = rng.choice(weight_opts)

        acc, enr = pairwise_accuracy(scores, labels, tune_ids, candidate, dims)
        if acc > best_tune_acc or (acc == best_tune_acc and enr > best_enrichment):
            best_weights   = candidate
            best_tune_acc  = acc
            best_enrichment = enr
            improvements += 1

    # Final holdout evaluation
    holdout_acc, holdout_enr = pairwise_accuracy(
        scores, labels, holdout_ids, best_weights, dims)

    return {
        "label":           label,
        "dims":            dims,
        "weights":         best_weights,
        "tune_accuracy":   round(best_tune_acc * 100, 2),
        "holdout_accuracy": round(holdout_acc * 100, 2),
        "holdout_enrichment": round(holdout_enr, 1),
        "improvements":    improvements,
        "v2_baseline_pct": round(V2_BASELINE * 100, 2),
        "vs_baseline":     round((holdout_acc - V2_BASELINE) * 100, 2),
        "gap_analysis":    gap,
        "optimized_at":    datetime.now(timezone.utc).isoformat(),
    }


# ─── Label Audit ──────────────────────────────────────────────────────────────

def run_label_audit(labels: dict, metadata: dict) -> list:
    """
    Cross-check labels against real-world outcomes from metadata.
    Flags shows where label and outcome conflict.
    """
    flags = []

    for show_id, label in labels.items():
        meta = metadata.get(show_id, {})
        if not meta:
            continue

        seasons  = meta.get("seasons")
        cancel   = meta.get("cancellation_status", "")
        title    = meta.get("title", show_id)
        conf     = meta.get("retrieval_confidence", "none")

        if conf in ("none", "very_low"):
            continue   # don't trust low-confidence metadata for audit

        issue = None

        if label == "loser" and seasons and seasons >= 5:
            issue = f"labeled loser but ran {seasons} seasons"
        elif label == "loser" and seasons and seasons >= 3 and cancel not in ("cancelled",):
            issue = f"labeled loser but ran {seasons} seasons without cancellation"
        elif label == "winner" and cancel == "cancelled" and seasons == 1:
            issue = "labeled winner but cancelled after 1 season"
        elif label == "winner" and seasons == 1 and cancel not in ("cancelled", None, ""):
            issue = f"labeled winner but only 1 season recorded"

        if issue:
            flags.append({
                "show_id":  show_id,
                "title":    title,
                "label":    label,
                "seasons":  seasons,
                "cancellation_status": cancel,
                "issue":    issue,
                "confidence": conf,
            })

    flags.sort(key=lambda x: (x["label"], -(x.get("seasons") or 0)))
    return flags


# ─── Reporting ────────────────────────────────────────────────────────────────

def print_results(result: dict):
    v2 = result["v2_baseline_pct"]
    h  = result["holdout_accuracy"]
    delta = result["vs_baseline"]
    arrow = "▲" if delta > 0 else ("▼" if delta < 0 else "—")

    print(f"\n{'='*65}")
    print(f"  OPTIMIZER RESULTS  [{result['label']}]")
    print(f"{'='*65}")
    print(f"  v2 baseline:       {v2:.2f}%  (5 dims)")
    print(f"  v3 holdout:        {h:.2f}%  ({len(result['dims'])} dims)  {arrow} {abs(delta):.2f}%")
    print(f"  winner enrichment: {result['holdout_enrichment']:.1f}%")
    print(f"  tune accuracy:     {result['tune_accuracy']:.2f}%")
    print(f"\n  Best weights:")
    sorted_w = sorted(result["weights"].items(), key=lambda x: -x[1])
    for dim, w in sorted_w:
        bar = "█" * int(w * 3)
        gap_val = result["gap_analysis"].get(dim, {}).get("gap", 0)
        tag = " ← NEW" if dim in NEW_DIMS else ""
        print(f"    {dim:<45} {w:>5.2f}  gap={gap_val:.3f}{tag}")
    print(f"\n  Improvements found: {result['improvements']}/{300}")
    print(f"{'='*65}\n")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GEM v3 Weight Optimizer")
    parser.add_argument("--dry-run",     action="store_true", help="Load data, show stats, no optimization")
    parser.add_argument("--genre",       type=str,   default=None, help="Optimize for a specific genre only")
    parser.add_argument("--genres",      action="store_true", help="Run stratified optimization per genre")
    parser.add_argument("--label-audit", action="store_true", help="Cross-check labels vs metadata outcomes")
    parser.add_argument("--iterations",  type=int,   default=300, help="Optimizer iterations (default 300)")
    parser.add_argument("--dims",        type=str,   default="all",
                        help="Which dims to use: 'all' (10), 'base' (5), 'new' (5), or comma-separated list")
    args = parser.parse_args()

    print("Loading data...")
    scores   = load_scores()
    labels   = load_labels()
    tune_ids, holdout_ids = load_split()
    metadata = load_metadata()

    # Filter to winner/loser only
    wl_labels = {k: v for k, v in labels.items() if v in ("winner", "loser")}

    # Determine dims to use
    if args.dims == "all":
        dims = ALL_DIMS
    elif args.dims == "base":
        dims = BASE_DIMS
    elif args.dims == "new":
        dims = NEW_DIMS
    else:
        dims = [d.strip() for d in args.dims.split(",")]

    # Coverage stats
    scored_ids = set(scores.keys())
    labeled_ids = set(wl_labels.keys())
    overlap = scored_ids & labeled_ids
    tune_overlap = overlap & tune_ids
    holdout_overlap = overlap & holdout_ids

    print(f"\n  v3 scored:         {len(scored_ids)}")
    print(f"  labeled (w/l):     {len(labeled_ids)}")
    print(f"  overlap:           {len(overlap)}")
    print(f"  tune usable:       {len(tune_overlap)}")
    print(f"  holdout usable:    {len(holdout_overlap)}")
    print(f"  dimensions:        {len(dims)}")
    print(f"  metadata loaded:   {len(metadata)}")

    if args.dry_run:
        print("\nDRY RUN — no optimization.")
        print("\nGap analysis (winner avg - loser avg):")
        gap = compute_gap_analysis(scores, wl_labels, dims)
        for d, g in gap.items():
            tag = " ← NEW" if d in NEW_DIMS else ""
            print(f"  {d:<45}  gap={g['gap']:.3f}  (w={g['winner_avg']:.2f} l={g['loser_avg']:.2f}){tag}")
        return

    if args.label_audit:
        print("\nRunning label audit...")
        flags = run_label_audit(labels, metadata)
        out = V3_DIR / "label_audit.json"
        out.write_text(json.dumps({
            "total_flags": len(flags),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "flags": flags,
        }, indent=2))
        print(f"\n  Total flags: {len(flags)}")
        if flags:
            print(f"\n  Top issues:")
            for f in flags[:15]:
                print(f"    [{f['label']}] {f['title'][:40]:<40}  {f['issue']}")
        print(f"\n  Full audit saved → {out}")
        return

    # ── Genre-stratified optimization ─────────────────────────────────────────
    if args.genres or args.genre:
        genre_map = defaultdict(list)
        for show_id, meta in metadata.items():
            if show_id not in scored_ids or show_id not in labeled_ids:
                continue
            fmt = meta.get("format_type") or "unknown"
            genre_map[fmt].append(show_id)

        print(f"\nGenre distribution in scored+labeled corpus:")
        for fmt, ids in sorted(genre_map.items(), key=lambda x: -len(x[1])):
            w = sum(1 for i in ids if wl_labels.get(i) == "winner")
            l = sum(1 for i in ids if wl_labels.get(i) == "loser")
            print(f"  {fmt:<25}  total={len(ids):>4}  winners={w:>3}  losers={l:>3}")

        target_genres = [args.genre] if args.genre else [
            fmt for fmt, ids in genre_map.items()
            if sum(1 for i in ids if wl_labels.get(i) == "winner") >= 5
        ]

        genre_results = {}
        for fmt in target_genres:
            genre_ids = set(genre_map[fmt])
            genre_tune    = tune_ids    & genre_ids
            genre_holdout = holdout_ids & genre_ids

            winners_tune = sum(1 for i in genre_tune    if wl_labels.get(i) == "winner")
            winners_hold = sum(1 for i in genre_holdout if wl_labels.get(i) == "winner")

            if winners_tune < 3 or winners_hold < 2:
                print(f"\n  Skipping {fmt}: insufficient winners (tune={winners_tune}, holdout={winners_hold})")
                continue

            print(f"\n  Optimizing: {fmt} (tune={len(genre_tune)}, holdout={len(genre_holdout)})...")
            result = optimize_weights(
                scores, wl_labels, genre_tune, genre_holdout,
                dims=dims, iterations=args.iterations, label=fmt,
            )
            genre_results[fmt] = result
            print_results(result)

        out = V3_DIR / "genre_weights.json"
        out.write_text(json.dumps(genre_results, indent=2))
        print(f"\nGenre weights saved → {out}")
        return

    # ── Global optimization ───────────────────────────────────────────────────
    print(f"\nRunning global optimization ({args.iterations} iterations, {len(dims)} dims)...")
    result = optimize_weights(
        scores, wl_labels, tune_ids, holdout_ids,
        dims=dims, iterations=args.iterations, label="global",
    )

    print_results(result)

    # Save
    out = V3_DIR / "best_weights.json"
    out.write_text(json.dumps(result, indent=2))
    print(f"Best config saved → {out}")

    # Also save gap analysis separately
    gap_out = V3_DIR / "gap_analysis.json"
    gap_out.write_text(json.dumps(result["gap_analysis"], indent=2))
    print(f"Gap analysis saved → {gap_out}")


if __name__ == "__main__":
    main()
