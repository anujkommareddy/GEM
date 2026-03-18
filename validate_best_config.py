#!/usr/bin/env python3
"""Run holdout validation on best config."""

import json
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from config import Config
from holdout_validator import HoldoutValidator


def main():
    """Run validation on best config v1."""
    print("\n" + "="*80)
    print("HOLDOUT VALIDATION: best_config_v1")
    print("="*80)

    # Load config
    config = Config()

    # Load all results
    print("\nLoading evaluation results...")
    all_results = {}
    per_script_dir = config.get_path("experiment_dir") / "live" / "per_script"

    for f in per_script_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if data.get("status") == "success":
                script_id = data.get("script_id")
                all_results[script_id] = data
        except Exception as e:
            print(f"  Warning: Failed to load {f.name}: {e}")

    print(f"  Loaded {len(all_results)} successful evaluations")

    # Initialize validator
    validator = HoldoutValidator(config, all_results)

    # Create stratified split
    print("\nCreating stratified 80/20 split...")
    tune_ids, holdout_ids = validator.create_stratified_split(test_size=0.2, seed=42)

    # Load current best config weights
    print("Loading current best config weights...")
    eval_config_file = config.config_dir / "evaluator_config.json"
    with open(eval_config_file) as f:
        eval_config = json.load(f)

    # Extract weights (they're at top level)
    weights = {
        "singular_vision": eval_config.get("singular_vision", 0.25),
        "character_depth": eval_config.get("character_depth", 0.20),
        "thematic_ambition": eval_config.get("thematic_ambition", 0.15),
        "emotional_specificity": eval_config.get("emotional_specificity", 0.15),
        "world_originality": eval_config.get("world_originality", 0.10),
        "dialogue_language": eval_config.get("dialogue_language", 0.10),
        "boldness": eval_config.get("boldness", 0.05),
        "transcendence_verdict": eval_config.get("transcendence_verdict", 0.0),
    }

    print("\nCurrent weights:")
    for dim, weight in weights.items():
        print(f"  {dim:25} {weight:.2f}")

    # Evaluate on both sets
    print("\n" + "="*80)
    print("EVALUATING ON TUNING AND HOLDOUT SETS")
    print("="*80)

    metrics = validator.evaluate_on_split(tune_ids, holdout_ids, weights)

    # Save validation report
    print("\nSaving validation report...")
    json_file, md_file = validator.save_validation_report(metrics, config_name="best_config_v1")

    # Print summary
    print("\n" + "="*80)
    print("VALIDATION SUMMARY")
    print("="*80)

    tune = metrics["tune"]
    holdout = metrics["holdout"]
    gap = tune["pairwise_accuracy"] - holdout["pairwise_accuracy"]

    print(f"\nPairwise Ranking Accuracy:")
    print(f"  Tuning set:  {tune['pairwise_accuracy']:.4f} ({tune['pairwise_correct']}/{tune['pairwise_total']})")
    print(f"  Holdout set: {holdout['pairwise_accuracy']:.4f} ({holdout['pairwise_correct']}/{holdout['pairwise_total']})")
    print(f"  Gap:         {gap:.4f}")

    if gap < 0.01:
        print(f"  → ✅ Excellent: < 1% gap (strong generalization)")
    elif gap < 0.05:
        print(f"  → ⚠️ Good: 1-5% gap (acceptable generalization)")
    elif gap < 0.10:
        print(f"  → ⚠️ Moderate: 5-10% gap (some overfitting)")
    else:
        print(f"  → ❌ Poor: > 10% gap (significant overfitting)")

    print(f"\nWinner Ranking (Top 10%):")
    tune_lift = tune["top_10_pct_winner_pct"] - tune["baseline_winner_pct"]
    holdout_lift = holdout["top_10_pct_winner_pct"] - holdout["baseline_winner_pct"]
    print(f"  Tuning:  {tune['top_10_pct_winners']}/{tune['top_10_pct_count']} winners ({tune['top_10_pct_winner_pct']:.1f}%) | Lift: +{tune_lift:.1f}%")
    print(f"  Holdout: {holdout['top_10_pct_winners']}/{holdout['top_10_pct_count']} winners ({holdout['top_10_pct_winner_pct']:.1f}%) | Lift: +{holdout_lift:.1f}%")

    if holdout_lift > 20:
        print(f"  → ✅ Strong: > 20% lift in top 10%")
    elif holdout_lift > 10:
        print(f"  → ⚠️ Moderate: 10-20% lift in top 10%")
    elif holdout_lift > 0:
        print(f"  → ⚠️ Weak: 0-10% lift in top 10%")
    else:
        print(f"  → ❌ No signal: negative/zero lift")

    print(f"\nConclusion:")
    if gap < 0.05 and holdout_lift > 10:
        print(f"  ✅ GENERALIZES WELL - Safe to continue tuning on tuning set only")
    elif gap < 0.10 and holdout_lift > 5:
        print(f"  ⚠️ ACCEPTABLE - Can continue tuning but watch for overfitting")
    else:
        print(f"  ❌ CONCERNING - May need to revisit approach")

    print(f"\nReports saved:")
    print(f"  JSON: {json_file}")
    print(f"  Markdown: {md_file}")
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    main()
