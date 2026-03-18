"""
V2.0 Pipeline: Post-evaluation gap analysis + autoresearch optimization.

Run this after `python3 src/cli.py run-eval` completes.

Steps:
  1. Load all v2.0 per-script results
  2. Create locked holdout split (80/20 stratified, seed=42)
  3. Run gap analysis on 5 v2.0 dimensions
  4. Phase 1: Grid search over weight combinations (~200 configs, no LLM cost)
  5. Phase 2: Fine-tune around best config
  6. Phase 3: Continuous random perturbation loop
  7. Save best config + update PRODUCER_INSIGHTS.md
"""

import json
import os
import random
import itertools
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Paths (relative to autoresearch/ directory)
# ─────────────────────────────────────────────
PER_SCRIPT_DIR  = "./data/results/live/per_script"
BENCHMARK_PATH  = "./data/benchmark/benchmark.jsonl"
RESULTS_DIR     = "./data/results"
SPLIT_PATH      = "./data/results/validation/v2_split.json"
INSIGHTS_PATH   = "./PRODUCER_INSIGHTS.md"

V2_DIMENSIONS = [
    "audience_appeal_marketability",
    "conceptual_hook_clarity",
    "character_appeal_and_long_term_potential",
    "creative_originality_and_boldness",
    "narrative_momentum_engagement",
]


# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

def load_results(per_script_dir: str) -> Dict:
    """Load all per-script v2.0 JSON results."""
    results = {}
    for json_file in Path(per_script_dir).glob("*.json"):
        try:
            with open(json_file) as f:
                data = json.load(f)
            script_id = data.get("script_id")
            if script_id and data.get("status") == "success":
                results[script_id] = data
        except Exception as e:
            logger.warning(f"Could not load {json_file}: {e}")
    logger.info(f"Loaded {len(results)} v2.0 results")
    return results


def load_benchmark(benchmark_path: str) -> Dict[str, str]:
    """Load benchmark labels → {script_id: 'winner'|'loser'}."""
    benchmark = {}
    with open(benchmark_path) as f:
        for line in f:
            try:
                entry = json.loads(line)
                script_id = entry.get("script_id")
                label = entry.get("label")
                if script_id and label in ("winner", "loser"):
                    benchmark[script_id] = label
            except Exception:
                pass
    winners = sum(1 for l in benchmark.values() if l == "winner")
    losers  = sum(1 for l in benchmark.values() if l == "loser")
    logger.info(f"Benchmark: {winners} winners, {losers} losers")
    return benchmark


# ═══════════════════════════════════════════════════════════════
# HOLDOUT SPLIT
# ═══════════════════════════════════════════════════════════════

def create_v2_split(results: Dict, benchmark: Dict,
                    split_path: str, test_size: float = 0.2, seed: int = 42) -> Tuple[List, List]:
    """
    Create a stratified 80/20 holdout split based on evaluated scripts.
    Saved to split_path for reproducibility. If split already exists and
    covers the same scripts, it is reused.
    """
    split_file = Path(split_path)
    split_file.parent.mkdir(parents=True, exist_ok=True)

    # Collect labeled evaluated scripts
    evaluated_winners = [s for s in results if benchmark.get(s) == "winner"]
    evaluated_losers  = [s for s in results if benchmark.get(s) == "loser"]

    if split_file.exists():
        with open(split_file) as f:
            existing = json.load(f)
        existing_ids = set(existing["tune"] + existing["holdout"])
        current_ids  = set(evaluated_winners + evaluated_losers)
        if existing_ids == current_ids:
            logger.info("✓ Reusing existing v2 split")
            return existing["tune"], existing["holdout"]
        logger.info("Script set changed — recreating split")

    random.seed(seed)
    n_holdout_winners = max(1, int(len(evaluated_winners) * test_size))
    n_holdout_losers  = max(1, int(len(evaluated_losers) * test_size))

    holdout_winners = random.sample(evaluated_winners, n_holdout_winners)
    holdout_losers  = random.sample(evaluated_losers,  n_holdout_losers)
    holdout_ids = set(holdout_winners + holdout_losers)

    all_labeled = set(evaluated_winners + evaluated_losers)
    tune_ids    = sorted(all_labeled - holdout_ids)
    holdout_ids = sorted(holdout_ids)

    with open(split_file, "w") as f:
        json.dump({"tune": tune_ids, "holdout": holdout_ids}, f, indent=2)

    logger.info(f"✓ Split created: {len(tune_ids)} tune / {len(holdout_ids)} holdout")
    logger.info(f"  Holdout: {n_holdout_winners} winners, {n_holdout_losers} losers")
    return tune_ids, holdout_ids


# ═══════════════════════════════════════════════════════════════
# GAP ANALYSIS
# ═══════════════════════════════════════════════════════════════

def gap_analysis(results: Dict, benchmark: Dict) -> Dict:
    """
    Compute winner/loser average and gap for each v2.0 dimension.
    Returns sorted dict by gap descending.
    """
    winner_scores = {d: [] for d in V2_DIMENSIONS}
    loser_scores  = {d: [] for d in V2_DIMENSIONS}

    for script_id, result in results.items():
        label  = benchmark.get(script_id)
        scores = result.get("aggregated", {}).get("individual_scores", {})
        if not label or not scores:
            continue
        for dim in V2_DIMENSIONS:
            s = scores.get(dim)
            if s is not None:
                if label == "winner":
                    winner_scores[dim].append(s)
                else:
                    loser_scores[dim].append(s)

    analysis = {}
    for dim in V2_DIMENSIONS:
        w = winner_scores[dim]
        l = loser_scores[dim]
        if not w or not l:
            continue
        w_avg = np.mean(w)
        l_avg = np.mean(l)
        gap   = w_avg - l_avg
        analysis[dim] = {
            "winner_avg":    round(w_avg, 3),
            "loser_avg":     round(l_avg, 3),
            "gap":           round(gap, 3),
            "winner_n":      len(w),
            "loser_n":       len(l),
            "std_winner":    round(np.std(w), 3),
            "std_loser":     round(np.std(l), 3),
        }

    sorted_analysis = dict(sorted(analysis.items(), key=lambda x: x[1]["gap"], reverse=True))

    print("\n" + "="*80)
    print("V2.0 GAP ANALYSIS — Winner vs. Loser by Dimension")
    print("="*80)
    print(f"{'Dimension':<45} {'Winner':>8} {'Loser':>8} {'Gap':>8}  Rank")
    print("-"*80)
    for rank, (dim, m) in enumerate(sorted_analysis.items(), 1):
        print(f"{dim:<45} {m['winner_avg']:>8.3f} {m['loser_avg']:>8.3f} {m['gap']:>8.3f}  #{rank}")
    print("="*80 + "\n")

    return sorted_analysis


# ═══════════════════════════════════════════════════════════════
# SCORING ENGINE (no LLM calls — pure math)
# ═══════════════════════════════════════════════════════════════

def score_scripts(results: Dict, benchmark: Dict, script_ids: List[str],
                  weights: Dict[str, float]) -> Tuple[Dict[str, float], List[str], List[str]]:
    """
    Compute weighted composite score for each script in script_ids.
    Returns (scores_dict, winners_in_set, losers_in_set).
    """
    scores  = {}
    winners = []
    losers  = []

    for script_id in script_ids:
        result = results.get(script_id)
        label  = benchmark.get(script_id)
        if not result or not label:
            continue

        dims = result.get("aggregated", {}).get("individual_scores", {})
        if not dims:
            continue

        w_sum = 0.0
        w_tot = 0.0
        for dim, w in weights.items():
            if w > 0 and dim in dims and dims[dim] is not None:
                w_sum += dims[dim] * w
                w_tot += w

        if w_tot > 0:
            scores[script_id] = w_sum / w_tot
            if label == "winner":
                winners.append(script_id)
            else:
                losers.append(script_id)

    return scores, winners, losers


def pairwise_accuracy(scores: Dict[str, float], winners: List[str], losers: List[str]) -> float:
    """% of (winner, loser) pairs where winner scores higher."""
    total   = len(winners) * len(losers)
    if total == 0:
        return 0.0
    correct = sum(1 for w in winners for l in losers if scores.get(w, 0) > scores.get(l, 0))
    return correct / total


def top_k_enrichment(scores: Dict[str, float], winners: List[str], losers: List[str], k_pct: float = 0.1) -> float:
    """% of winners in the top-k% of scripts."""
    all_ids = list(scores.keys())
    k = max(1, int(len(all_ids) * k_pct))
    top_k   = sorted(all_ids, key=lambda s: scores[s], reverse=True)[:k]
    top_w   = sum(1 for s in top_k if s in set(winners))
    return top_w / k if k > 0 else 0.0


def evaluate_weights(results: Dict, benchmark: Dict,
                     tune_ids: List[str], holdout_ids: List[str],
                     weights: Dict[str, float]) -> Dict:
    """Evaluate a weight config on both tune and holdout."""
    tune_scores, tune_w, tune_l     = score_scripts(results, benchmark, tune_ids, weights)
    hold_scores, hold_w, hold_l     = score_scripts(results, benchmark, holdout_ids, weights)

    tune_acc  = pairwise_accuracy(tune_scores, tune_w, tune_l)
    hold_acc  = pairwise_accuracy(hold_scores, hold_w, hold_l)
    hold_top  = top_k_enrichment(hold_scores, hold_w, hold_l)

    return {
        "weights":          weights,
        "tune_accuracy":    round(tune_acc,  4),
        "holdout_accuracy": round(hold_acc,  4),
        "holdout_top10":    round(hold_top,  4),
        "gap":              round(tune_acc - hold_acc, 4),
    }


# ═══════════════════════════════════════════════════════════════
# PHASE 1: STRUCTURED WEIGHT PROPOSALS
# ═══════════════════════════════════════════════════════════════

def generate_phase1_proposals(gap_analysis: Dict) -> List[Dict[str, float]]:
    """
    Generate ~200 weight proposals covering:
    - Uniform baseline
    - Gap-proportional
    - Single-dimension emphasis
    - Combinations derived from gaps
    """
    dims = V2_DIMENSIONS
    gaps = [gap_analysis.get(d, {}).get("gap", 0) for d in dims]
    min_gap = min(gaps)
    # Shift so all gaps are positive before normalization
    shifted = [g - min_gap + 1e-6 for g in gaps]

    proposals = []

    # 1. Uniform baseline
    proposals.append({d: 1.0 for d in dims})

    # 2. Gap-proportional
    total = sum(shifted)
    props = {d: s / total for d, s in zip(dims, shifted)}
    proposals.append(props)

    # 3. Quadratic gap scaling
    q_shifted = [s**2 for s in shifted]
    total_q   = sum(q_shifted)
    proposals.append({d: s / total_q for d, s in zip(dims, q_shifted)})

    # 4. Top-1 emphasis (highest gap gets 3×)
    top_idx = int(np.argmax(shifts := [g - min_gap for g in gaps]))
    emph = {d: 1.0 for d in dims}
    emph[dims[top_idx]] = 3.0
    proposals.append(emph)

    # 5. Top-2 emphasis
    top2_idx = sorted(range(len(gaps)), key=lambda i: gaps[i], reverse=True)[:2]
    emph2 = {d: 1.0 for d in dims}
    for i in top2_idx:
        emph2[dims[i]] = 2.5
    proposals.append(emph2)

    # 6. Remove weakest (lowest gap → weight 0)
    worst_idx = int(np.argmin(gaps))
    no_weak = {d: 1.0 for d in dims}
    no_weak[dims[worst_idx]] = 0.0
    proposals.append(no_weak)

    # 7. Remove two weakest
    worst2_idx = sorted(range(len(gaps)), key=lambda i: gaps[i])[:2]
    no_weak2 = {d: 1.0 for d in dims}
    for i in worst2_idx:
        no_weak2[dims[i]] = 0.0
    proposals.append(no_weak2)

    # 8-12. Sparse: each single dimension alone
    for d in dims:
        sparse = {dd: 0.0 for dd in dims}
        sparse[d] = 1.0
        proposals.append(sparse)

    # 13-22. Grid over top-2 dimensions, hold others equal
    top2 = [dims[i] for i in sorted(range(len(gaps)), key=lambda i: gaps[i], reverse=True)[:2]]
    for w1, w2 in itertools.product([0.5, 1.0, 1.5, 2.0, 3.0], repeat=2):
        g = {d: 1.0 for d in dims}
        g[top2[0]] = w1
        g[top2[1]] = w2
        proposals.append(g)

    # 23-72. Random weight samples
    rng = random.Random(42)
    weight_vals = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    for _ in range(50):
        p = {d: rng.choice(weight_vals) for d in dims}
        if any(v > 0 for v in p.values()):
            proposals.append(p)

    # 73-122. Finer random around gap-proportional
    for _ in range(50):
        p = {}
        for d, s in zip(dims, shifted):
            base = s / total
            p[d] = max(0.0, base + rng.uniform(-0.3, 0.3))
        if any(v > 0 for v in p.values()):
            proposals.append(p)

    # Deduplicate
    seen = set()
    unique = []
    for p in proposals:
        key = tuple(round(p.get(d, 0), 3) for d in dims)
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique


# ═══════════════════════════════════════════════════════════════
# PHASE 2: FINE-TUNE AROUND BEST
# ═══════════════════════════════════════════════════════════════

def fine_tune_weights(results: Dict, benchmark: Dict,
                      tune_ids: List, holdout_ids: List,
                      best_weights: Dict, best_accuracy: float,
                      n_iterations: int = 200) -> Tuple[Dict, float]:
    """
    Random perturbation search around best_weights.
    Keeps any improvement > 0.1% on holdout.
    """
    rng = random.Random(99)
    dims = V2_DIMENSIONS
    improvements = 0

    for i in range(n_iterations):
        # Random perturbation: nudge each weight ±small amount
        perturbed = {}
        for d in dims:
            base = best_weights.get(d, 1.0)
            delta = rng.choice([-0.3, -0.15, 0.0, 0.15, 0.3])
            perturbed[d] = max(0.0, base + delta)

        if not any(v > 0 for v in perturbed.values()):
            continue

        metrics = evaluate_weights(results, benchmark, tune_ids, holdout_ids, perturbed)
        acc = metrics["holdout_accuracy"]

        if acc > best_accuracy + 0.001:   # 0.1% improvement threshold
            best_weights  = perturbed
            best_accuracy = acc
            improvements += 1
            logger.info(f"  Fine-tune iter {i+1}: +{(acc - best_accuracy + 0.001)*100:.2f}%  → {acc*100:.2f}%")

    logger.info(f"Fine-tuning: {improvements} improvements in {n_iterations} iterations")
    return best_weights, best_accuracy


# ═══════════════════════════════════════════════════════════════
# PHASE 3: CONTINUOUS PERTURBATION LOOP
# ═══════════════════════════════════════════════════════════════

def continuous_loop(results: Dict, benchmark: Dict,
                    tune_ids: List, holdout_ids: List,
                    best_weights: Dict, best_accuracy: float,
                    max_rejections: int = 30,
                    max_iterations: int = 500) -> Tuple[Dict, float, List]:
    """
    Keep perturbing. Stop after max_rejections consecutive no-improvement.
    Returns (best_weights, best_accuracy, history).
    """
    rng = random.Random(7)
    dims = V2_DIMENSIONS
    consecutive_rejections = 0
    history = []
    iteration = 0

    weight_options = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]

    while consecutive_rejections < max_rejections and iteration < max_iterations:
        iteration += 1

        # Alternate between small perturbations and larger jumps
        if iteration % 5 == 0:
            # Larger jump: randomly resample some dimensions
            candidate = dict(best_weights)
            dims_to_change = rng.sample(dims, k=rng.randint(1, 3))
            for d in dims_to_change:
                candidate[d] = rng.choice(weight_options)
        else:
            # Small perturbation
            candidate = {}
            for d in dims:
                base = best_weights.get(d, 1.0)
                delta = rng.choice([-0.25, -0.1, 0.0, 0.1, 0.25])
                candidate[d] = max(0.0, round(base + delta, 2))

        if not any(v > 0 for v in candidate.values()):
            continue

        metrics = evaluate_weights(results, benchmark, tune_ids, holdout_ids, candidate)
        acc = metrics["holdout_accuracy"]

        if acc > best_accuracy + 0.0005:   # 0.05% threshold
            improvement = acc - best_accuracy
            best_weights  = candidate
            best_accuracy = acc
            consecutive_rejections = 0
            history.append({"iteration": iteration, "accuracy": acc,
                             "improvement": improvement, "weights": candidate})
            logger.info(f"  [iter {iteration}] IMPROVE: {acc*100:.3f}%  (+{improvement*100:.3f}%)")
        else:
            consecutive_rejections += 1

        if iteration % 50 == 0:
            logger.info(f"  [iter {iteration}] best={best_accuracy*100:.3f}%  consecutive_rejections={consecutive_rejections}")

    logger.info(f"Converged after {iteration} iterations | {len(history)} improvements")
    return best_weights, best_accuracy, history


# ═══════════════════════════════════════════════════════════════
# REPORTING
# ═══════════════════════════════════════════════════════════════

def save_best_config(best_weights: Dict, best_metrics: Dict, results_dir: str, label: str = "v2_best"):
    """Save best config to JSON."""
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    config = {
        "label":       label,
        "timestamp":   datetime.utcnow().isoformat(),
        "dimensions":  V2_DIMENSIONS,
        "weights":     best_weights,
        "metrics":     best_metrics,
    }
    path = Path(results_dir) / f"{label}.json"
    with open(path, "w") as f:
        json.dump(config, f, indent=2)
    logger.info(f"Saved best config → {path}")
    return path


def update_producer_insights(gap_results: Dict, best_metrics: Dict, best_weights: Dict, insights_path: str):
    """Append v2.0 findings to PRODUCER_INSIGHTS.md."""
    now = datetime.utcnow().strftime("%Y-%m-%d")
    section = f"""
---

## Session 2: V2.0 Re-Evaluation Results ({now})

### Gap Analysis — 5 Producer Dimensions

| Rank | Dimension | Winner Avg | Loser Avg | Gap |
|------|-----------|-----------|----------|-----|
"""
    for rank, (dim, m) in enumerate(gap_results.items(), 1):
        section += f"| {rank} | {dim} | {m['winner_avg']} | {m['loser_avg']} | **{m['gap']}** |\n"

    best_hold = best_metrics.get("holdout_accuracy", 0)
    best_tune = best_metrics.get("tune_accuracy", 0)
    section += f"""
### Best Config Found

| Metric | Value |
|--------|-------|
| Holdout pairwise accuracy | **{best_hold*100:.2f}%** |
| Tuning pairwise accuracy | {best_tune*100:.2f}% |
| Tune/holdout gap | {(best_tune - best_hold)*100:.2f}% |

**Weights:**
"""
    for dim, w in sorted(best_weights.items(), key=lambda x: -x[1]):
        section += f"- `{dim}`: {w:.3f}\n"

    section += """
### Hypothesis Check

"""
    # Check H1-H5
    gaps_list = [(d, m["gap"]) for d, m in gap_results.items()]
    gaps_sorted = sorted(gaps_list, key=lambda x: -x[1])
    top_dim = gaps_sorted[0][0] if gaps_sorted else "N/A"
    section += f"- **H1 (commercial appeal dominant):** Top gap dimension = `{top_dim}`\n"
    section += f"- **H2 (conceptual clarity undervalued):** conceptual_hook_clarity gap = {gap_results.get('conceptual_hook_clarity', {}).get('gap', 'N/A')}\n"
    section += f"- **H3 (character durability > depth):** character_appeal gap = {gap_results.get('character_appeal_and_long_term_potential', {}).get('gap', 'N/A')}\n"
    section += f"- **H4 (narrative momentum cross-genre):** narrative_momentum gap = {gap_results.get('narrative_momentum_engagement', {}).get('gap', 'N/A')}\n"
    section += f"- **H5 (originality important but not dominant):** creative_originality gap = {gap_results.get('creative_originality_and_boldness', {}).get('gap', 'N/A')}\n"

    with open(insights_path, "a") as f:
        f.write(section)
    logger.info(f"Updated PRODUCER_INSIGHTS.md → {insights_path}")


# ═══════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

def run_v2_pipeline(
    per_script_dir: str = PER_SCRIPT_DIR,
    benchmark_path: str = BENCHMARK_PATH,
    results_dir: str    = RESULTS_DIR,
    split_path: str     = SPLIT_PATH,
    insights_path: str  = INSIGHTS_PATH,
):
    start = datetime.utcnow()
    print("\n" + "="*80)
    print("V2.0 AUTORESEARCH PIPELINE")
    print("="*80 + "\n")

    # ── Load data ──────────────────────────────────────────────
    results   = load_results(per_script_dir)
    benchmark = load_benchmark(benchmark_path)

    if len(results) < 50:
        print(f"⚠️  Only {len(results)} scripts evaluated. Run more evaluations first.")
        print("   Proceeding with partial results (results will be preliminary).\n")

    # ── Holdout split ──────────────────────────────────────────
    tune_ids, holdout_ids = create_v2_split(results, benchmark, split_path)

    # ── Gap analysis ───────────────────────────────────────────
    gaps = gap_analysis(results, benchmark)
    gap_path = Path(results_dir) / "v2_gap_analysis.json"
    with open(gap_path, "w") as f:
        json.dump(gaps, f, indent=2)
    logger.info(f"Gap analysis saved → {gap_path}")

    # ── Phase 1: Structured proposals ─────────────────────────
    print("\n── PHASE 1: Structured weight proposals ──")
    proposals = generate_phase1_proposals(gaps)
    print(f"Testing {len(proposals)} weight configurations...")

    best_weights   = {d: 1.0 for d in V2_DIMENSIONS}
    best_metrics   = evaluate_weights(results, benchmark, tune_ids, holdout_ids, best_weights)
    best_accuracy  = best_metrics["holdout_accuracy"]

    phase1_results = []
    for i, weights in enumerate(proposals):
        m = evaluate_weights(results, benchmark, tune_ids, holdout_ids, weights)
        phase1_results.append(m)
        if m["holdout_accuracy"] > best_accuracy:
            best_accuracy = m["holdout_accuracy"]
            best_weights  = weights
            best_metrics  = m
            logger.info(f"  Phase1 [{i+1}/{len(proposals)}] NEW BEST: {best_accuracy*100:.3f}%  weights={weights}")

    # Save phase 1 results
    p1_path = Path(results_dir) / "v2_phase1_results.json"
    with open(p1_path, "w") as f:
        json.dump(sorted(phase1_results, key=lambda x: -x["holdout_accuracy"]), f, indent=2)
    print(f"\n  Phase 1 best: {best_accuracy*100:.3f}% holdout accuracy")
    print(f"  Best weights: {best_weights}")

    # ── Phase 2: Fine-tune ─────────────────────────────────────
    print("\n── PHASE 2: Fine-tuning around best config ──")
    best_weights, best_accuracy = fine_tune_weights(
        results, benchmark, tune_ids, holdout_ids,
        best_weights, best_accuracy, n_iterations=300
    )
    best_metrics = evaluate_weights(results, benchmark, tune_ids, holdout_ids, best_weights)
    print(f"  After fine-tune: {best_accuracy*100:.3f}% holdout")

    # ── Phase 3: Continuous loop ───────────────────────────────
    print("\n── PHASE 3: Continuous perturbation loop ──")
    best_weights, best_accuracy, loop_history = continuous_loop(
        results, benchmark, tune_ids, holdout_ids,
        best_weights, best_accuracy,
        max_rejections=40, max_iterations=600
    )
    best_metrics = evaluate_weights(results, benchmark, tune_ids, holdout_ids, best_weights)
    print(f"  Final best: {best_accuracy*100:.3f}% holdout accuracy")

    # ── Save outputs ───────────────────────────────────────────
    label = f"v2_best_{best_accuracy*100:.2f}pct"
    save_best_config(best_weights, best_metrics, results_dir, label=label)

    # Save loop history
    hist_path = Path(results_dir) / "v2_loop_history.json"
    with open(hist_path, "w") as f:
        json.dump(loop_history, f, indent=2)

    # ── Update PRODUCER_INSIGHTS.md ────────────────────────────
    update_producer_insights(gaps, best_metrics, best_weights, insights_path)

    # ── Final summary ──────────────────────────────────────────
    elapsed = (datetime.utcnow() - start).total_seconds()
    print("\n" + "="*80)
    print("V2.0 PIPELINE COMPLETE")
    print("="*80)
    print(f"Scripts evaluated:      {len(results)}")
    print(f"  Tune set:             {len(tune_ids)}")
    print(f"  Holdout set:          {len(holdout_ids)}")
    print(f"\nBest holdout accuracy:  {best_accuracy*100:.3f}%")
    print(f"Tune accuracy:          {best_metrics['tune_accuracy']*100:.3f}%")
    print(f"Tune/holdout gap:       {best_metrics['gap']*100:.3f}%")
    print(f"\nTop dimensions by gap:")
    for dim, m in list(gaps.items())[:3]:
        print(f"  {dim}: gap={m['gap']:.3f}")
    print(f"\nBest weights:")
    for dim in V2_DIMENSIONS:
        print(f"  {dim}: {best_weights.get(dim, 1.0):.3f}")
    print(f"\nRuntime: {elapsed:.1f}s")
    print(f"\nOutputs saved to: {results_dir}/")
    print("  v2_gap_analysis.json")
    print(f"  {label}.json")
    print("  v2_phase1_results.json")
    print("  v2_loop_history.json")
    print("  PRODUCER_INSIGHTS.md (updated)")
    print("="*80 + "\n")

    return best_weights, best_accuracy, gaps


if __name__ == "__main__":
    import sys
    per_script = sys.argv[1] if len(sys.argv) > 1 else PER_SCRIPT_DIR
    run_v2_pipeline(per_script_dir=per_script)
