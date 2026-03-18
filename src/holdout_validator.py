"""Holdout validation for tuning generalization."""

import json
from pathlib import Path
from typing import Dict, Set, Tuple
import random


class HoldoutValidator:
    """Create stratified holdout split and validate generalization."""

    def __init__(self, config, all_results: Dict):
        """
        Initialize validator.

        Args:
            config: Config object
            all_results: Dict of script_id -> evaluation result
        """
        self.config = config
        self.all_results = all_results
        self.benchmark_file = config.get_path("benchmark_file")
        self.validation_dir = config.get_path("experiment_dir") / "validation"
        self.validation_dir.mkdir(parents=True, exist_ok=True)

    def create_stratified_split(self, test_size: float = 0.2, seed: int = 42) -> Tuple[Set[str], Set[str]]:
        """
        Create stratified 80/20 split preserving winner/loser ratio.

        Args:
            test_size: Proportion for holdout (default 0.2 = 20%)
            seed: Random seed for reproducibility

        Returns:
            (tune_ids, holdout_ids) — two sets of script IDs
        """
        random.seed(seed)

        # Load labels
        winners = []
        losers = []

        with open(self.benchmark_file) as f:
            for line in f:
                data = json.loads(line)
                script_id = data["script_id"]

                # Only include scripts with results
                if script_id not in self.all_results:
                    continue

                if data.get("label") == "winner":
                    winners.append(script_id)
                elif data.get("label") == "loser":
                    losers.append(script_id)

        # Stratified split
        num_test_winners = max(1, int(len(winners) * test_size))
        num_test_losers = max(1, int(len(losers) * test_size))

        holdout_winners = set(random.sample(winners, num_test_winners))
        holdout_losers = set(random.sample(losers, num_test_losers))
        holdout_ids = holdout_winners | holdout_losers

        tune_ids = set(self.all_results.keys()) - holdout_ids

        print(f"\n{'='*70}")
        print("STRATIFIED HOLDOUT SPLIT")
        print(f"{'='*70}")
        print(f"Total evaluated: {len(self.all_results)}")
        print(f"Tuning set: {len(tune_ids)} scripts")
        print(f"  Winners: {len(holdout_winners & {s for s in tune_ids if self._get_label(s) == 'winner'})}")
        print(f"  Losers: {len({s for s in tune_ids if self._get_label(s) == 'loser'})}")
        print(f"Holdout set: {len(holdout_ids)} scripts")
        print(f"  Winners: {len(holdout_winners)}")
        print(f"  Losers: {len(holdout_losers)}")
        print(f"{'='*70}\n")

        # Save split
        split_file = self.validation_dir / "split.json"
        with open(split_file, "w") as f:
            json.dump(
                {"tune": sorted(list(tune_ids)), "holdout": sorted(list(holdout_ids))},
                f,
                indent=2,
            )

        return tune_ids, holdout_ids

    def _get_label(self, script_id: str) -> str:
        """Get label from benchmark."""
        with open(self.benchmark_file) as f:
            for line in f:
                data = json.loads(line)
                if data["script_id"] == script_id:
                    return data.get("label")
        return None

    def evaluate_on_split(
        self, tune_ids: Set[str], holdout_ids: Set[str], weights: Dict[str, float]
    ) -> Dict:
        """
        Evaluate config on both tuning and holdout sets.

        Args:
            tune_ids: Script IDs for tuning set
            holdout_ids: Script IDs for holdout set
            weights: Current dimension weights

        Returns:
            Dict with metrics for both sets
        """
        results = {}

        for set_name, script_ids in [("tune", tune_ids), ("holdout", holdout_ids)]:
            print(f"\nEvaluating on {set_name} set ({len(script_ids)} scripts)...")

            # Re-aggregate with current weights
            scores = {}
            for script_id in script_ids:
                if script_id not in self.all_results:
                    continue

                result = self.all_results[script_id]
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

            # Load labels for this set
            labels = {}
            with open(self.benchmark_file) as f:
                for line in f:
                    data = json.loads(line)
                    if data["script_id"] in script_ids:
                        labels[data["script_id"]] = data.get("label")

            # Calculate pairwise accuracy
            winners = [s for s, l in labels.items() if l == "winner" and s in scores]
            losers = [s for s, l in labels.items() if l == "loser" and s in scores]

            correct = 0
            total = len(winners) * len(losers)
            for w in winners:
                for l in losers:
                    if scores[w] > scores[l]:
                        correct += 1

            pairwise_acc = correct / total if total > 0 else 0

            # Top 10% analysis
            top_10_pct = max(1, int(len(scores) * 0.1))
            top_scripts = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_10_pct]
            top_winner_count = sum(1 for s, _ in top_scripts if labels.get(s) == "winner")
            baseline_winner_pct = (len(winners) / len(scores)) * 100 if scores else 0

            results[set_name] = {
                "num_scripts": len(script_ids),
                "num_winners": len(winners),
                "num_losers": len(losers),
                "pairwise_accuracy": pairwise_acc,
                "pairwise_correct": correct,
                "pairwise_total": total,
                "top_10_pct_count": top_10_pct,
                "top_10_pct_winners": top_winner_count,
                "top_10_pct_winner_pct": (top_winner_count / top_10_pct) * 100 if top_10_pct > 0 else 0,
                "baseline_winner_pct": baseline_winner_pct,
            }

            print(f"  Pairwise accuracy: {pairwise_acc:.4f} ({correct}/{total})")
            print(f"  Winners in top 10%: {top_winner_count}/{top_10_pct} ({(top_winner_count/top_10_pct)*100:.1f}%)")
            print(f"  Baseline winner %: {baseline_winner_pct:.1f}%")

        return results

    def save_validation_report(self, metrics: Dict, config_name: str = "best_config_v1"):
        """Save validation results to report."""
        report = {
            "config_name": config_name,
            "validation_date": "2026-03-17",
            "metrics": metrics,
            "interpretation": self._interpret_results(metrics),
        }

        report_file = self.validation_dir / f"{config_name}_validation.json"
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)

        # Also save markdown report
        md_file = self.validation_dir / f"{config_name}_validation.md"
        with open(md_file, "w") as f:
            f.write(self._format_markdown_report(config_name, metrics))

        print(f"\n✅ Validation report saved:")
        print(f"  JSON: {report_file}")
        print(f"  Markdown: {md_file}")

        return report_file, md_file

    def _interpret_results(self, metrics: Dict) -> str:
        """Interpret whether results generalize."""
        tune_acc = metrics["tune"]["pairwise_accuracy"]
        holdout_acc = metrics["holdout"]["pairwise_accuracy"]
        gap = tune_acc - holdout_acc

        tune_top10 = metrics["tune"]["top_10_pct_winner_pct"]
        holdout_top10 = metrics["holdout"]["top_10_pct_winner_pct"]
        baseline_holdout = metrics["holdout"]["baseline_winner_pct"]

        interpretation = []

        # Pairwise accuracy gap
        if gap < 0.01:
            interpretation.append("✅ Excellent generalization: tuning/holdout gap < 1%")
        elif gap < 0.05:
            interpretation.append("⚠️ Good generalization: tuning/holdout gap 1-5%")
        elif gap < 0.10:
            interpretation.append("⚠️ Moderate overfitting: tuning/holdout gap 5-10%")
        else:
            interpretation.append("❌ Significant overfitting: tuning/holdout gap > 10%")

        # Winner ranking
        lift = holdout_top10 - baseline_holdout
        if lift > 20:
            interpretation.append(f"✅ Strong winner ranking: +{lift:.1f}% lift in top 10%")
        elif lift > 10:
            interpretation.append(f"⚠️ Moderate winner ranking: +{lift:.1f}% lift in top 10%")
        elif lift > 0:
            interpretation.append(f"⚠️ Weak winner ranking: +{lift:.1f}% lift in top 10%")
        else:
            interpretation.append(f"❌ No ranking signal: {lift:.1f}% lift in top 10%")

        return " | ".join(interpretation)

    def _format_markdown_report(self, config_name: str, metrics: Dict) -> str:
        """Format results as markdown."""
        tune = metrics["tune"]
        holdout = metrics["holdout"]

        return f"""# Holdout Validation Report

**Config:** {config_name}
**Date:** 2026-03-17

---

## Pairwise Ranking Accuracy (THE KEY METRIC)

| Set | Accuracy | Winners/Losers | Pairs Correct |
|---|---|---|---|
| Tuning | {tune['pairwise_accuracy']:.4f} | {tune['num_winners']}/{tune['num_losers']} | {tune['pairwise_correct']}/{tune['pairwise_total']} |
| **Holdout** | **{holdout['pairwise_accuracy']:.4f}** | **{holdout['num_winners']}/{holdout['num_losers']}** | **{holdout['pairwise_correct']}/{holdout['pairwise_total']}** |
| **Gap** | **{tune['pairwise_accuracy'] - holdout['pairwise_accuracy']:.4f}** | | |

---

## Winner Ranking (Top 10%)

| Set | Winners in Top 10% | Pct | Baseline Winner % | Lift |
|---|---|---|---|---|
| Tuning | {tune['top_10_pct_winners']}/{tune['top_10_pct_count']} | {tune['top_10_pct_winner_pct']:.1f}% | {tune['baseline_winner_pct']:.1f}% | +{tune['top_10_pct_winner_pct'] - tune['baseline_winner_pct']:.1f}% |
| **Holdout** | **{holdout['top_10_pct_winners']}/{holdout['top_10_pct_count']}** | **{holdout['top_10_pct_winner_pct']:.1f}%** | **{holdout['baseline_winner_pct']:.1f}%** | **+{holdout['top_10_pct_winner_pct'] - holdout['baseline_winner_pct']:.1f}%** |

---

## Interpretation

{metrics.get('interpretation', 'No interpretation available')}

---

## Key Questions

1. **Does it generalize?**
   - Tuning/holdout gap: {tune['pairwise_accuracy'] - holdout['pairwise_accuracy']:.4f}
   - Answer: {'✅ YES' if (tune['pairwise_accuracy'] - holdout['pairwise_accuracy']) < 0.05 else '⚠️ MAYBE' if (tune['pairwise_accuracy'] - holdout['pairwise_accuracy']) < 0.10 else '❌ NO'}

2. **Do winners appear at the top?**
   - Holdout top 10% winner %: {holdout['top_10_pct_winner_pct']:.1f}%
   - Baseline: {holdout['baseline_winner_pct']:.1f}%
   - Lift: +{holdout['top_10_pct_winner_pct'] - holdout['baseline_winner_pct']:.1f}%
   - Answer: {'✅ YES - Strong signal' if (holdout['top_10_pct_winner_pct'] - holdout['baseline_winner_pct']) > 20 else '⚠️ MAYBE - Weak signal' if (holdout['top_10_pct_winner_pct'] - holdout['baseline_winner_pct']) > 10 else '❌ NO - No signal'}

3. **Ready to ship?**
   - Holdout pairwise accuracy: {holdout['pairwise_accuracy']:.4f} ({holdout['pairwise_accuracy']*100:.2f}%)
   - Answer: {'✅ YES - Strong performance' if holdout['pairwise_accuracy'] > 0.81 else '⚠️ MAYBE - Acceptable performance' if holdout['pairwise_accuracy'] > 0.79 else '❌ NO - More tuning needed'}
"""
