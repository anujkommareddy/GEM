#!/usr/bin/env python3
"""Compare baseline vs tuned weights on holdout set."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import Config
from auto_proposer import AutoProposer


def evaluate_weights(all_results, holdout_ids, weights, label):
    """Evaluate weights on holdout set."""
    # Re-aggregate with weights
    scores = {}
    for script_id in holdout_ids:
        if script_id not in all_results:
            continue

        result = all_results[script_id]
        dims = result.get("aggregated", {}).get("individual_scores", {})
        if not dims:
            continue

        weighted_sum = 0
        weight_total = 0
        for dim, score in dims.items():
            weight = weights.get(dim, 0)
            if weight > 0 and score is not None:
                weighted_sum += score * weight
                weight_total += weight

        if weight_total > 0:
            scores[script_id] = weighted_sum / weight_total

    # Load labels
    config = Config()
    labels = {}
    with open(config.get_path("benchmark_file")) as f:
        for line in f:
            data = json.loads(line)
            if data["script_id"] in holdout_ids:
                labels[data["script_id"]] = data.get("label")

    # Pairwise accuracy
    winners = [s for s, l in labels.items() if l == "winner" and s in scores]
    losers = [s for s, l in labels.items() if l == "loser" and s in scores]

    correct = 0
    total = len(winners) * len(losers)
    for w in winners:
        for l in losers:
            if scores[w] > scores[l]:
                correct += 1

    pairwise_acc = correct / total if total > 0 else 0

    # Top 10%
    top_10_pct = max(1, int(len(scores) * 0.1))
    top_scripts = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_10_pct]
    top_winner_count = sum(1 for s, _ in top_scripts if labels.get(s) == "winner")

    print(f"\n{label}:")
    print(f"  Pairwise accuracy: {pairwise_acc:.4f} ({correct}/{total})")
    print(f"  Winners in top 10%: {top_winner_count}/{top_10_pct} ({(top_winner_count/top_10_pct)*100:.1f}%)")
    print(f"  Baseline winner %: {(len(winners)/len(scores)*100):.1f}%")

    return pairwise_acc, (top_winner_count / top_10_pct) * 100 if top_10_pct > 0 else 0


def main():
    """Compare baseline vs tuned on holdout."""
    print("\n" + "="*80)
    print("BASELINE vs TUNED WEIGHTS COMPARISON (Holdout Set)")
    print("="*80)

    config = Config()

    # Load results and split
    print("\nLoading data...")
    all_results = {}
    per_script_dir = config.get_path("experiment_dir") / "live" / "per_script"
    for f in per_script_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if data.get("status") == "success":
                all_results[data.get("script_id")] = data
        except:
            pass

    # Load split
    split_file = config.get_path("experiment_dir") / "validation" / "split.json"
    with open(split_file) as f:
        split = json.load(f)
    holdout_ids = set(split["holdout"])

    print(f"Holdout set: {len(holdout_ids)} scripts")

    # Baseline weights (from AutoProposer)
    baseline_weights = AutoProposer.BASELINE_WEIGHTS
    print(f"\nBaseline weights:")
    for dim, w in baseline_weights.items():
        print(f"  {dim:25} {w:.2f}")

    # Tuned weights
    eval_config_file = config.config_dir / "evaluator_config.json"
    with open(eval_config_file) as f:
        eval_config = json.load(f)

    tuned_weights = {
        "singular_vision": eval_config.get("singular_vision", 0.25),
        "character_depth": eval_config.get("character_depth", 0.20),
        "thematic_ambition": eval_config.get("thematic_ambition", 0.15),
        "emotional_specificity": eval_config.get("emotional_specificity", 0.15),
        "world_originality": eval_config.get("world_originality", 0.10),
        "dialogue_language": eval_config.get("dialogue_language", 0.10),
        "boldness": eval_config.get("boldness", 0.05),
        "transcendence_verdict": eval_config.get("transcendence_verdict", 0.0),
    }
    print(f"\nTuned weights:")
    for dim, w in tuned_weights.items():
        change = w - baseline_weights.get(dim, 0)
        marker = " ✅" if change != 0 else ""
        print(f"  {dim:25} {w:.2f} ({change:+.2f}){marker}")

    # Evaluate both
    print("\n" + "="*80)
    print("HOLDOUT SET PERFORMANCE")
    print("="*80)

    baseline_acc, baseline_top10 = evaluate_weights(all_results, holdout_ids, baseline_weights, "BASELINE")
    tuned_acc, tuned_top10 = evaluate_weights(all_results, holdout_ids, tuned_weights, "TUNED")

    # Compare
    print("\n" + "="*80)
    print("IMPROVEMENT ON HOLDOUT SET")
    print("="*80)
    acc_gain = tuned_acc - baseline_acc
    top10_gain = tuned_top10 - baseline_top10

    print(f"\nPairwise accuracy:")
    print(f"  Baseline: {baseline_acc:.4f}")
    print(f"  Tuned:    {tuned_acc:.4f}")
    print(f"  Gain:     {acc_gain:+.4f} ({acc_gain/baseline_acc*100:+.2f}%)")

    print(f"\nWinner ranking (top 10%):")
    print(f"  Baseline: {baseline_top10:.1f}%")
    print(f"  Tuned:    {tuned_top10:.1f}%")
    print(f"  Gain:     {top10_gain:+.1f} percentage points")

    # Conclusion
    print(f"\n" + "="*80)
    if acc_gain > 0 and top10_gain > 0:
        print(f"✅ TUNING IMPROVES HOLDOUT PERFORMANCE")
        print(f"   Tuned weights beat baseline on unseen data")
    else:
        print(f"⚠️ TUNING HURTS HOLDOUT PERFORMANCE")
        print(f"   Baseline may be better generalization")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
