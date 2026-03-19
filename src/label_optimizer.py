"""
label_optimizer.py — Auto-research system for label promotion criteria

Tests different criteria for promoting loser-labeled shows to winner,
measuring holdout pairwise accuracy for each. Hill-climbs to find the
combination of criteria that maximizes accuracy.

No new LLM calls — uses existing v3 scores + Wikipedia metadata.

Usage:
    python3 src/label_optimizer.py                  # Full hill-climb
    python3 src/label_optimizer.py --dry-run        # Show candidates, no changes
    python3 src/label_optimizer.py --explore        # Test all single criteria, rank by delta
    python3 src/label_optimizer.py --apply          # Apply best config to labels_v2.jsonl
    python3 src/label_optimizer.py --iterations 200 # More hill-climb iterations (default 100)

Output:
    data/scoring/v3_expanded/label_opt_results.json  — full results per criterion
    data/scoring/v3_expanded/best_label_config.json  — best promotion set found
"""

import argparse
import json
import random
import copy
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Tuple, Optional

# ─── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR     = Path(".")
V3_DIR       = BASE_DIR / "data/scoring/v3_expanded"
PER_SCRIPT   = V3_DIR / "per_script"
LABELS_FILE  = BASE_DIR / "data/labels/labels_v2.jsonl"
SPLIT_FILE   = BASE_DIR / "data/results/validation/v2_split.json"
METADATA_DIR = BASE_DIR / "data/metadata"

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

# Networks associated with prestige/transcendent TV
PRESTIGE_NETWORKS = {
    "hbo", "fx", "amc", "showtime", "netflix", "hulu", "amazon",
    "apple tv+", "starz", "sundance", "bbc", "bbc two", "channel 4",
}

# Genres that are almost never transcendent (filter out false positives)
NON_TRANSCENDENT_GENRES = {
    "reality", "reality tv", "game show", "talk show", "documentary",
    "news", "sports", "cooking", "home improvement", "dating",
    "competition", "variety", "quiz", "infotainment",
}

# ─── Data Loading ───────────────────────────────────────────────────────────────

def load_scores() -> Dict[str, Dict[str, float]]:
    scores = {}
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
            pass
    return scores


def load_labels() -> Dict[str, str]:
    labels = {}
    for line in LABELS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        labels[r["show_id"]] = r["label_v2"]
    return labels


def load_label_records() -> List[dict]:
    records = []
    for line in LABELS_FILE.read_text().splitlines():
        if not line.strip():
            continue
        records.append(json.loads(line))
    return records


def load_split() -> Tuple[Set[str], Set[str]]:
    split = json.loads(SPLIT_FILE.read_text())
    return set(split["tune"]), set(split["holdout"])


def load_metadata() -> Dict[str, dict]:
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


# ─── Evaluation ─────────────────────────────────────────────────────────────────

def pairwise_accuracy(scores: dict, labels: dict, ids: Set[str],
                      weights: Optional[Dict[str, float]] = None) -> float:
    """Compute pairwise winner>loser accuracy on given id set."""
    if weights is None:
        weights = {d: 1.0 for d in ALL_DIMS}

    scored = []
    for sid in ids:
        if sid not in scores or sid not in labels:
            continue
        if labels[sid] == "middle":
            continue
        s = scores[sid]
        w = sum(s.get(d, 0) * weights.get(d, 1.0) for d in ALL_DIMS)
        scored.append((w, labels[sid]))

    winners = [w for w, l in scored if l == "winner"]
    losers  = [w for w, l in scored if l == "loser"]
    if not winners or not losers:
        return 0.0

    correct = sum(1 for w in winners for l in losers if w > l)
    return correct / (len(winners) * len(losers))


def optimize_weights_quick(scores: dict, labels: dict,
                           tune_ids: Set[str], n_iter: int = 200) -> Dict[str, float]:
    """Fast weight hill-climb on tune set. Returns best weights."""
    weights = {d: 1.0 for d in ALL_DIMS}
    best_acc = pairwise_accuracy(scores, labels, tune_ids, weights)

    for _ in range(n_iter):
        w2 = copy.deepcopy(weights)
        # Mutate 1-2 dims
        dims_to_mutate = random.sample(ALL_DIMS, k=random.randint(1, 2))
        for dim in dims_to_mutate:
            delta = random.choice([-1.0, -0.5, -0.25, 0.25, 0.5, 1.0])
            w2[dim] = max(0.0, w2[dim] + delta)
        acc = pairwise_accuracy(scores, labels, tune_ids, w2)
        if acc >= best_acc:
            weights = w2
            best_acc = acc

    return weights


# ─── Promotion Criteria ─────────────────────────────────────────────────────────

def composite(scores: dict, show_id: str) -> float:
    s = scores.get(show_id, {})
    vals = [s.get(d, 0) for d in ALL_DIMS if d in s]
    return sum(vals) / len(vals) if vals else 0.0


def dim_score(scores: dict, show_id: str, dim: str) -> float:
    return scores.get(show_id, {}).get(dim, 0.0)


def is_prestige_network(meta: dict, show_id: str) -> bool:
    m = meta.get(show_id, {})
    networks = [n.lower() for n in m.get("original_network", [])]
    return any(any(p in n for p in PRESTIGE_NETWORKS) for n in networks)


def is_non_transcendent_genre(meta: dict, show_id: str) -> bool:
    m = meta.get(show_id, {})
    genres = [g.lower() for g in m.get("genres", [])]
    return any(any(nt in g for nt in NON_TRANSCENDENT_GENRES) for g in genres)


def seasons_count(meta: dict, show_id: str) -> int:
    return meta.get(show_id, {}).get("seasons") or 0


def build_candidate_criteria(scores: dict, meta: dict,
                              current_losers: Set[str]) -> List[dict]:
    """
    Build a list of promotion criteria, each with a name, description,
    and function that returns True if a show should be promoted.
    """
    criteria = []

    # ── Score threshold criteria ──────────────────────────────────────────────
    for thresh in [8.5, 8.3, 8.1, 7.9, 7.7]:
        criteria.append({
            "name": f"composite_gt_{thresh}",
            "desc": f"Composite v3 score > {thresh}",
            "fn": lambda sid, t=thresh: composite(scores, sid) > t,
        })

    # ── Dimension-specific criteria ───────────────────────────────────────────
    for dim_short, dim_full in [
        ("tonal", "tonal_specificity"),
        ("resonant", "resonant_originality"),
        ("creative", "creative_originality_and_boldness"),
        ("character", "character_appeal_and_long_term_potential"),
        ("latent", "latent_depth_slow_burn_potential"),
    ]:
        for thresh in [8.5, 8.0]:
            criteria.append({
                "name": f"{dim_short}_gt_{thresh}",
                "desc": f"{dim_full} > {thresh}",
                "fn": lambda sid, d=dim_full, t=thresh: dim_score(scores, sid, d) > t,
            })

    # ── Combined: top-2 new dims ──────────────────────────────────────────────
    for t1, t2 in [(8.5, 8.0), (8.0, 8.0), (8.5, 8.5)]:
        criteria.append({
            "name": f"tonal_{t1}_and_resonant_{t2}",
            "desc": f"tonal_specificity > {t1} AND resonant_originality > {t2}",
            "fn": lambda sid, ta=t1, rb=t2: (
                dim_score(scores, sid, "tonal_specificity") > ta and
                dim_score(scores, sid, "resonant_originality") > rb
            ),
        })

    # ── Prestige network + score ──────────────────────────────────────────────
    for thresh in [8.0, 7.8, 7.5]:
        criteria.append({
            "name": f"prestige_network_and_composite_{thresh}",
            "desc": f"Prestige network (HBO/FX/AMC/Netflix/etc) AND composite > {thresh}",
            "fn": lambda sid, t=thresh: (
                composite(scores, sid) > t and
                is_prestige_network(meta, sid)
            ),
        })

    # ── Exclude non-transcendent genres ──────────────────────────────────────
    for thresh in [8.0, 7.8]:
        criteria.append({
            "name": f"not_reality_composite_{thresh}",
            "desc": f"Not reality/game/talk genre AND composite > {thresh}",
            "fn": lambda sid, t=thresh: (
                composite(scores, sid) > t and
                not is_non_transcendent_genre(meta, sid)
            ),
        })

    # ── Short run (cancelled before bloat) + high score ──────────────────────
    for thresh in [8.0, 7.8]:
        criteria.append({
            "name": f"critical_run_1_to_5_seasons_composite_{thresh}",
            "desc": f"1-5 seasons (critical darling run) AND composite > {thresh}",
            "fn": lambda sid, t=thresh: (
                composite(scores, sid) > t and
                1 <= seasons_count(meta, sid) <= 5
            ),
        })

    # ── Full package: prestige + not-reality + score ──────────────────────────
    for thresh in [7.8, 8.0]:
        criteria.append({
            "name": f"prestige_not_reality_composite_{thresh}",
            "desc": f"Prestige network AND not reality genre AND composite > {thresh}",
            "fn": lambda sid, t=thresh: (
                composite(scores, sid) > t and
                is_prestige_network(meta, sid) and
                not is_non_transcendent_genre(meta, sid)
            ),
        })

    # ── Creative + tonal combo ────────────────────────────────────────────────
    criteria.append({
        "name": "creative_and_tonal_both_gt_8",
        "desc": "creative_originality > 8 AND tonal_specificity > 8",
        "fn": lambda sid: (
            dim_score(scores, sid, "creative_originality_and_boldness") > 8.0 and
            dim_score(scores, sid, "tonal_specificity") > 8.0
        ),
    })

    criteria.append({
        "name": "top3_dims_avg_gt_8.5",
        "desc": "Average of top 3 dimension scores > 8.5",
        "fn": lambda sid: (
            sorted([scores.get(sid, {}).get(d, 0) for d in ALL_DIMS], reverse=True)[:3]
            and sum(sorted([scores.get(sid, {}).get(d, 0) for d in ALL_DIMS], reverse=True)[:3]) / 3 > 8.5
        ),
    })

    return criteria


# ─── Hill-Climbing Label Optimizer ─────────────────────────────────────────────

def apply_criterion(base_labels: dict, criterion: dict,
                    losers: Set[str]) -> dict:
    """Return new label dict with criterion applied to current losers."""
    new_labels = copy.deepcopy(base_labels)
    promoted = set()
    for sid in losers:
        try:
            if criterion["fn"](sid):
                new_labels[sid] = "winner"
                promoted.add(sid)
        except Exception:
            pass
    return new_labels, promoted


def evaluate_criterion(scores: dict, base_labels: dict, criterion: dict,
                       losers: Set[str], tune_ids: Set[str], holdout_ids: Set[str],
                       n_weight_iter: int = 150) -> dict:
    """Apply criterion, optimize weights, return accuracy delta."""
    new_labels, promoted = apply_criterion(base_labels, criterion, losers)

    if not promoted:
        return {"name": criterion["name"], "promoted": 0, "delta_holdout": 0.0,
                "holdout_acc": 0.0, "tune_acc": 0.0, "promoted_ids": []}

    weights = optimize_weights_quick(scores, new_labels, tune_ids, n_weight_iter)
    tune_acc = pairwise_accuracy(scores, new_labels, tune_ids, weights)
    holdout_acc = pairwise_accuracy(scores, new_labels, holdout_ids, weights)

    return {
        "name":         criterion["name"],
        "desc":         criterion["desc"],
        "promoted":     len(promoted),
        "promoted_ids": sorted(promoted),
        "tune_acc":     round(tune_acc * 100, 3),
        "holdout_acc":  round(holdout_acc * 100, 3),
        "delta_holdout": None,  # filled in by caller
    }


# ─── Main Modes ─────────────────────────────────────────────────────────────────

def run_explore(scores, labels, meta, tune_ids, holdout_ids, n_weight_iter=150):
    """Test every criterion independently. Rank by holdout delta."""
    current_losers = {sid for sid, l in labels.items() if l == "loser"}

    # Baseline
    base_weights = optimize_weights_quick(scores, labels, tune_ids, n_weight_iter)
    base_holdout = pairwise_accuracy(scores, labels, holdout_ids, base_weights)
    base_tune    = pairwise_accuracy(scores, labels, tune_ids, base_weights)
    print(f"\nBaseline → tune={base_tune*100:.2f}%  holdout={base_holdout*100:.2f}%")
    print(f"Candidate losers: {len(current_losers)}\n")

    criteria = build_candidate_criteria(scores, meta, current_losers)
    print(f"Testing {len(criteria)} criteria...\n")

    results = []
    for i, crit in enumerate(criteria, 1):
        r = evaluate_criterion(scores, labels, crit, current_losers,
                               tune_ids, holdout_ids, n_weight_iter)
        r["delta_holdout"] = round(r["holdout_acc"] - base_holdout * 100, 3)
        results.append(r)
        sign = "▲" if r["delta_holdout"] > 0 else ("▼" if r["delta_holdout"] < 0 else "─")
        print(f"  [{i:2}/{len(criteria)}] {r['name']:<45}  "
              f"promoted={r['promoted']:3}  "
              f"holdout={r['holdout_acc']:.2f}%  {sign}{abs(r['delta_holdout']):.3f}pp")

    results.sort(key=lambda x: x["delta_holdout"], reverse=True)

    print(f"\n{'='*80}")
    print(f"EXPLORE RESULTS — ranked by holdout accuracy delta")
    print(f"{'='*80}")
    print(f"{'Criterion':<45}  {'Promoted':>8}  {'Holdout':>8}  {'Delta':>8}")
    print("-" * 80)
    for r in results[:15]:
        sign = "▲" if r["delta_holdout"] > 0 else ("▼" if r["delta_holdout"] < 0 else "─")
        print(f"  {r['name']:<43}  {r['promoted']:>8}  "
              f"{r['holdout_acc']:>7.2f}%  {sign}{abs(r['delta_holdout']):.3f}pp")

    # Save full results
    out = {
        "generated_at":   datetime.now().isoformat(),
        "baseline_holdout": round(base_holdout * 100, 3),
        "baseline_tune":    round(base_tune * 100, 3),
        "results":          results,
    }
    outfile = V3_DIR / "label_opt_explore.json"
    outfile.write_text(json.dumps(out, indent=2))
    print(f"\nFull results saved → {outfile}")
    return results, base_holdout


def run_hillclimb(scores, labels, meta, tune_ids, holdout_ids,
                  n_iter=100, n_weight_iter=150):
    """
    Hill-climb: greedily add promotion criteria one at a time as long as
    holdout accuracy improves. Then try random combinations.
    """
    current_labels = copy.deepcopy(labels)
    current_losers = {sid for sid, l in current_labels.items() if l == "loser"}

    base_weights  = optimize_weights_quick(scores, current_labels, tune_ids, n_weight_iter)
    best_holdout  = pairwise_accuracy(scores, current_labels, holdout_ids, base_weights)
    best_weights  = base_weights
    best_labels   = copy.deepcopy(current_labels)
    applied       = []
    all_promoted  = set()

    print(f"\nStarting hill-climb")
    print(f"Baseline holdout: {best_holdout*100:.3f}%")
    print(f"Candidate losers: {len(current_losers)}\n")

    criteria = build_candidate_criteria(scores, meta, current_losers)

    # ── Greedy phase: try each criterion, keep if it helps ───────────────────
    print("Phase 1: Greedy single-criterion search")
    print("-" * 60)
    improved_this_round = True
    while improved_this_round:
        improved_this_round = False
        random.shuffle(criteria)
        for crit in criteria:
            r = evaluate_criterion(scores, current_labels, crit,
                                   current_losers, tune_ids, holdout_ids, n_weight_iter)
            if r["promoted"] == 0:
                continue
            holdout = r["holdout_acc"] / 100
            if holdout > best_holdout + 0.001:  # require at least 0.1pp gain
                best_holdout = holdout
                new_labels, promoted = apply_criterion(current_labels, crit, current_losers)
                current_labels = new_labels
                current_losers -= promoted
                all_promoted |= promoted
                best_labels = copy.deepcopy(current_labels)
                # Re-optimize weights with new labels
                best_weights = optimize_weights_quick(scores, current_labels,
                                                      tune_ids, n_weight_iter)
                applied.append({
                    "criterion": crit["name"],
                    "desc": crit["desc"],
                    "promoted": len(promoted),
                    "new_holdout": round(best_holdout * 100, 3),
                })
                improved_this_round = True
                print(f"  ✓ KEPT  {crit['name']:<43}  "
                      f"+{len(promoted)} shows  "
                      f"→ holdout={best_holdout*100:.3f}%")
                break  # restart with updated labels
        else:
            pass  # exhausted all criteria without improvement

    # ── Random perturbation phase ──────────────────────────────────────────────
    print(f"\nPhase 2: Random perturbation ({n_iter} trials)")
    print("-" * 60)
    improvements = 0
    for trial in range(n_iter):
        # Try promoting a random subset of remaining high-score losers
        hi_losers = [sid for sid in current_losers
                     if composite(scores, sid) > 7.5]
        if not hi_losers:
            break
        sample_size = random.randint(1, min(10, len(hi_losers)))
        sample = random.sample(hi_losers, sample_size)

        trial_labels = copy.deepcopy(current_labels)
        for sid in sample:
            trial_labels[sid] = "winner"

        weights = optimize_weights_quick(scores, trial_labels, tune_ids, n_weight_iter)
        holdout = pairwise_accuracy(scores, trial_labels, holdout_ids, weights)

        if holdout > best_holdout + 0.001:
            best_holdout = holdout
            current_labels = trial_labels
            current_losers -= set(sample)
            all_promoted |= set(sample)
            best_weights = weights
            best_labels = copy.deepcopy(current_labels)
            improvements += 1
            applied.append({
                "criterion": f"random_trial_{trial}",
                "desc": f"Random promotion of {sample_size} shows",
                "promoted": len(sample),
                "promoted_ids": sample,
                "new_holdout": round(best_holdout * 100, 3),
            })
            print(f"  ✓ Trial {trial:3}  promoted={sample_size}  "
                  f"→ holdout={best_holdout*100:.3f}%")

    print(f"\n  Random phase: {improvements}/{n_iter} improvements")

    # ── Final summary ──────────────────────────────────────────────────────────
    final_winners = {sid for sid, l in best_labels.items() if l == "winner"}
    original_winners = {sid for sid, l in labels.items() if l == "winner"}
    net_new = final_winners - original_winners

    print(f"\n{'='*70}")
    print(f"HILL-CLIMB COMPLETE")
    print(f"{'='*70}")
    print(f"  Starting holdout:  {pairwise_accuracy(scores, labels, holdout_ids)*100:.3f}%")
    print(f"  Final holdout:     {best_holdout*100:.3f}%")
    print(f"  Improvement:       +{(best_holdout - pairwise_accuracy(scores, labels, holdout_ids))*100:.3f}pp")
    print(f"  Shows promoted:    {len(net_new)}")
    print(f"  Total winners:     {len(final_winners)}")
    print(f"\n  Criteria applied:")
    for a in applied:
        print(f"    • {a['criterion']:<45} +{a['promoted']} → {a['new_holdout']}%")

    # Save best config
    out = {
        "generated_at":     datetime.now().isoformat(),
        "starting_holdout": round(pairwise_accuracy(scores, labels, holdout_ids) * 100, 3),
        "final_holdout":    round(best_holdout * 100, 3),
        "total_winners":    len(final_winners),
        "net_new_winners":  len(net_new),
        "promoted_ids":     sorted(net_new),
        "criteria_applied": applied,
        "best_weights":     best_weights,
    }
    outfile = V3_DIR / "best_label_config.json"
    outfile.write_text(json.dumps(out, indent=2))
    print(f"\nBest config saved → {outfile}")

    return best_labels, best_weights, best_holdout, net_new


def apply_to_labels_file(best_labels: dict, net_new: Set[str]):
    """Write promoted labels back to labels_v2.jsonl."""
    import shutil
    shutil.copy(LABELS_FILE, LABELS_FILE.with_suffix(".jsonl.pre_label_opt"))
    records = load_label_records()
    updated = []
    changed = 0
    for r in records:
        sid = r["show_id"]
        if sid in net_new and r["label_v2"] == "loser":
            r = dict(r)
            r["label_v2"] = "winner"
            r["label_v2_confidence"] = "medium"
            r["needs_review"] = True
            r["labeled_by"] = "label_optimizer_v1"
            r["labeled_at"] = datetime.now().strftime("%Y-%m-%d")
            changed += 1
        updated.append(r)
    with open(LABELS_FILE, "w") as f:
        for r in updated:
            f.write(json.dumps(r) + "\n")
    print(f"\n✓ Applied {changed} label changes to {LABELS_FILE}")
    print(f"  Backup saved: {LABELS_FILE.with_suffix('.jsonl.pre_label_opt')}")


# ─── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GEM Label Optimizer")
    parser.add_argument("--dry-run",    action="store_true",
                        help="Show candidates and baseline, no optimization")
    parser.add_argument("--explore",    action="store_true",
                        help="Test all criteria independently, rank by delta")
    parser.add_argument("--apply",      action="store_true",
                        help="Apply best_label_config.json to labels_v2.jsonl")
    parser.add_argument("--iterations", type=int, default=100,
                        help="Random perturbation trials (default: 100)")
    parser.add_argument("--weight-iter", type=int, default=150,
                        help="Weight optimizer iterations per eval (default: 150)")
    args = parser.parse_args()

    print("Loading data...")
    scores   = load_scores()
    labels   = load_labels()
    meta     = load_metadata()
    tune_ids, holdout_ids = load_split()

    scored_ids = set(scores.keys())
    winners = {sid for sid, l in labels.items() if l == "winner" and sid in scored_ids}
    losers  = {sid for sid, l in labels.items() if l == "loser"  and sid in scored_ids}

    print(f"  v3 scored:      {len(scores)}")
    print(f"  winners:        {len(winners)}")
    print(f"  losers:         {len(losers)}")
    print(f"  tune usable:    {len(tune_ids & (winners | losers))}")
    print(f"  holdout usable: {len(holdout_ids & (winners | losers))}")

    if args.dry_run:
        # Show high-scoring losers as candidates
        candidates = [(sid, composite(scores, sid))
                      for sid in losers if composite(scores, sid) > 7.5]
        candidates.sort(key=lambda x: x[1], reverse=True)
        print(f"\nHigh-scoring losers (composite > 7.5): {len(candidates)}")
        print(f"\n{'Show':<55} {'Composite':>9}  {'Network':>20}  {'Seasons':>7}")
        print("-" * 100)
        for sid, comp in candidates[:30]:
            m = meta.get(sid, {})
            raw_net = m.get("original_network", [])
            network = ", ".join(raw_net if isinstance(raw_net, list) else [str(raw_net)])[:20]
            seasons = m.get("seasons") or "?"
            print(f"  {sid[:55]:<55} {comp:>9.2f}  {network:>20}  {seasons!s:>7}")
        return

    if args.apply:
        cfg_file = V3_DIR / "best_label_config.json"
        if not cfg_file.exists():
            print("ERROR: Run hill-climb first to generate best_label_config.json")
            return
        cfg = json.loads(cfg_file.read_text())
        net_new = set(cfg["promoted_ids"])
        best_labels = copy.deepcopy(labels)
        for sid in net_new:
            best_labels[sid] = "winner"
        apply_to_labels_file(best_labels, net_new)
        print(f"\n✓ Applied {len(net_new)} promotions to labels file")
        return

    if args.explore:
        run_explore(scores, labels, meta, tune_ids, holdout_ids, args.weight_iter)
        return

    # Default: full hill-climb
    best_labels, best_weights, best_holdout, net_new = run_hillclimb(
        scores, labels, meta, tune_ids, holdout_ids,
        n_iter=args.iterations, n_weight_iter=args.weight_iter
    )

    if net_new:
        ans = input(f"\nApply {len(net_new)} label changes to labels_v2.jsonl? [y/N] ").strip().lower()
        if ans == "y":
            apply_to_labels_file(best_labels, net_new)
        else:
            print("Not applied. Run with --apply to apply later.")


if __name__ == "__main__":
    main()
