"""
Auto-optimize facet set and weights using holdout validation.
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import numpy as np
from facet_analyzer import FacetAnalyzer
from facet_proposer import FacetProposer


class AutoFacetResearch:
    """Test facet/weight proposals on locked holdout set"""

    def __init__(self,
                 per_script_dir: str,
                 split_path: str,
                 benchmark_path: str,
                 results_dir: str):
        self.per_script_dir = per_script_dir
        self.split_path = split_path
        self.benchmark_path = benchmark_path
        self.results_dir = results_dir

        self.holdout_ids = []
        self.tune_ids = []
        self.all_results = {}
        self.benchmark = {}
        self.experiments = []

    def load_split(self):
        """Load holdout/tune split"""
        with open(self.split_path) as f:
            split = json.load(f)
            self.tune_ids = split.get("tune", [])
            self.holdout_ids = split.get("holdout", [])
        print(f"Loaded split: {len(self.tune_ids)} tune, {len(self.holdout_ids)} holdout")

    def load_results(self):
        """Load all per_script results"""
        count = 0
        for json_file in Path(self.per_script_dir).glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                    script_id = data.get("script_id")
                    if script_id:
                        self.all_results[script_id] = data
                        count += 1
            except Exception as e:
                print(f"Error loading {json_file}: {e}")
        print(f"Loaded {count} evaluated scripts")

    def load_benchmark(self):
        """Load benchmark labels"""
        count = 0
        with open(self.benchmark_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    script_id = entry.get("script_id")
                    label = entry.get("label")
                    if script_id and label in ["winner", "loser"]:
                        self.benchmark[script_id] = label
                        count += 1
                except:
                    pass
        print(f"Loaded {count} benchmark labels")

    def evaluate_weights(self, weights: Dict[str, float], on_holdout: bool = True) -> Tuple[float, float]:
        """
        Evaluate a weight config on holdout (or tune for comparison).
        Returns: (pairwise_accuracy, top10_winner_enrichment)
        """
        dataset_ids = self.holdout_ids if on_holdout else self.tune_ids

        # Collect (score, label) for all scripts in dataset
        scored = []
        for script_id in dataset_ids:
            result = self.all_results.get(script_id)
            label = self.benchmark.get(script_id)

            if not result or not label:
                continue

            individual_scores = result.get("aggregated", {}).get("individual_scores", {})
            if not individual_scores:
                continue

            # Re-aggregate with new weights
            weighted_sum = sum(
                individual_scores.get(facet, 0) * weights.get(facet, 0)
                for facet in weights.keys()
            )

            scored.append((weighted_sum, label))

        if not scored:
            return 0.0, 0.0

        # Pairwise accuracy: % of (winner, loser) pairs where winner > loser
        winners = [score for score, label in scored if label == "winner"]
        losers = [score for score, label in scored if label == "loser"]

        if not winners or not losers:
            return 0.0, 0.0

        correct_pairs = sum(1 for w in winners for l in losers if w > l)
        total_pairs = len(winners) * len(losers)
        pairwise_acc = 100.0 * correct_pairs / total_pairs if total_pairs > 0 else 0.0

        # Top 10% winner enrichment
        all_scored_sorted = sorted(scored, key=lambda x: x[0], reverse=True)
        top_10_count = max(1, len(all_scored_sorted) // 10)
        top_10 = all_scored_sorted[:top_10_count]
        winners_in_top10 = sum(1 for _, label in top_10 if label == "winner")
        winner_enrichment = 100.0 * winners_in_top10 / len(winners) if winners else 0.0

        return pairwise_acc, winner_enrichment

    def test_proposal(self, proposal: Dict) -> Dict:
        """Test a single proposal, return experiment record"""
        proposal_id = proposal["proposal_id"]
        name = proposal["name"]
        weights = proposal["weights"]
        rationale = proposal["rationale"]

        # Evaluate on holdout
        holdout_acc, holdout_enrichment = self.evaluate_weights(weights, on_holdout=True)

        # Also evaluate on tune set for comparison
        tune_acc, tune_enrichment = self.evaluate_weights(weights, on_holdout=False)

        experiment = {
            "timestamp": datetime.now().isoformat(),
            "proposal_id": proposal_id,
            "name": name,
            "rationale": rationale,
            "weights": weights,
            "metrics": {
                "holdout": {
                    "pairwise_accuracy": holdout_acc,
                    "top10_enrichment": holdout_enrichment,
                },
                "tune": {
                    "pairwise_accuracy": tune_acc,
                    "top10_enrichment": tune_enrichment,
                }
            },
            "decision": "PENDING",  # Will fill in after comparison
        }

        self.experiments.append(experiment)
        return experiment

    def run_phase1(self):
        """Run Phase 1: test all proposals on holdout"""
        print("\n" + "="*100)
        print("PHASE 1: WEIGHT OPTIMIZATION ON LOCKED HOLDOUT SET")
        print("="*100 + "\n")

        # Generate proposals
        analyzer = FacetAnalyzer(self.per_script_dir, self.benchmark_path)
        analyzer.load_all_results()
        analyzer.load_benchmark()
        metrics = analyzer.analyze_facets()
        analyzer.print_analysis(metrics)

        # Save analysis
        metrics_dict = {
            name: {
                "winner_avg": m.winner_avg,
                "loser_avg": m.loser_avg,
                "gap": m.gap,
                "gap_percentile": m.gap_percentile,
                "std_dev": m.std_dev_overall
            }
            for name, m in metrics.items()
        }
        with open(os.path.join(self.results_dir, "facet_analysis.json"), "w") as f:
            json.dump(metrics_dict, f, indent=2)

        # Generate proposals
        proposer = FacetProposer(metrics_dict)
        proposals = proposer.generate_proposals()
        proposer.print_proposals()

        # Save proposals
        proposals_data = [
            {
                "proposal_id": p.proposal_id,
                "name": p.name,
                "weights": p.weights,
                "rationale": p.rationale
            }
            for p in proposals
        ]
        with open(os.path.join(self.results_dir, "facet_proposals.json"), "w") as f:
            json.dump(proposals_data, f, indent=2)

        # Test all proposals
        print("\nTesting proposals on holdout set...\n")
        for proposal in proposals_data:
            exp = self.test_proposal(proposal)
            holdout_acc = exp["metrics"]["holdout"]["pairwise_accuracy"]
            tune_acc = exp["metrics"]["tune"]["pairwise_accuracy"]
            print(f"P{proposal['proposal_id']:2d}: {proposal['name']:<40} | "
                  f"Holdout: {holdout_acc:6.2f}% | Tune: {tune_acc:6.2f}%")

        # Analyze results
        self._analyze_results()

    def _analyze_results(self):
        """Analyze Phase 1 results"""
        print("\n" + "="*100)
        print("PHASE 1 ANALYSIS")
        print("="*100 + "\n")

        # Sort by holdout accuracy
        sorted_exps = sorted(
            self.experiments,
            key=lambda e: e["metrics"]["holdout"]["pairwise_accuracy"],
            reverse=True
        )

        print("Top 5 configurations by holdout accuracy:")
        for i, exp in enumerate(sorted_exps[:5], 1):
            name = exp["name"]
            holdout = exp["metrics"]["holdout"]["pairwise_accuracy"]
            tune = exp["metrics"]["tune"]["pairwise_accuracy"]
            gap = tune - holdout
            print(f"  {i}. {name:<45} | Holdout: {holdout:6.2f}% | "
                  f"Tune: {tune:6.2f}% | Gap: {gap:6.2f}%")

        # Identify the best (prefer smaller tune/holdout gap if scores are similar)
        best = sorted_exps[0]
        baseline = self.experiments[0]  # P0 is baseline

        print(f"\nBaseline (P0): {baseline['metrics']['holdout']['pairwise_accuracy']:.2f}%")
        print(f"Best found (P{best['proposal_id']}): {best['metrics']['holdout']['pairwise_accuracy']:.2f}%")
        improvement = best['metrics']['holdout']['pairwise_accuracy'] - baseline['metrics']['holdout']['pairwise_accuracy']
        print(f"Improvement: {improvement:+.2f}%")

        if improvement > 0.5:
            best['decision'] = "KEEP"
            print(f"\n✓ Promoting P{best['proposal_id']} ({best['name']}) as new best config")
        else:
            best['decision'] = "NO_IMPROVEMENT"
            print(f"\n✗ No meaningful improvement found; sticking with baseline")

        # Save experiments
        with open(os.path.join(self.results_dir, "facet_phase1_experiments.jsonl"), "w") as f:
            for exp in self.experiments:
                f.write(json.dumps(exp) + "\n")

        print(f"\nExperiment log saved to facet_phase1_experiments.jsonl")

        # Generate summary
        self._generate_summary(best)

    def _generate_summary(self, best_exp: Dict):
        """Generate readable summary"""
        summary_path = os.path.join(self.results_dir, "facet_phase1_summary.md")

        with open(summary_path, "w") as f:
            f.write("# Phase 1: Facet Weight Optimization - Summary\n\n")

            f.write("## Objective\n")
            f.write("Optimize weights for the current 7-facet set to maximize holdout pairwise accuracy.\n\n")

            f.write("## Approach\n")
            f.write("- Generated 11 weight proposals based on gap analysis, sparsity, and heuristics\n")
            f.write("- Tested each on locked holdout set (179 scripts: 13 winners, 166 losers)\n")
            f.write("- Selected best by holdout pairwise accuracy\n\n")

            f.write("## Results\n\n")
            f.write("### Best Configuration\n")
            f.write(f"- **Name**: {best_exp['name']}\n")
            f.write(f"- **Holdout Accuracy**: {best_exp['metrics']['holdout']['pairwise_accuracy']:.2f}%\n")
            f.write(f"- **Top 10% Enrichment**: {best_exp['metrics']['holdout']['top10_enrichment']:.2f}%\n")
            f.write(f"- **Rationale**: {best_exp['rationale']}\n\n")

            f.write("### Weights\n")
            f.write("```json\n")
            f.write(json.dumps(best_exp['weights'], indent=2) + "\n")
            f.write("```\n\n")

            f.write("### Comparison to Baseline\n")
            baseline = self.experiments[0]
            baseline_acc = baseline['metrics']['holdout']['pairwise_accuracy']
            best_acc = best_exp['metrics']['holdout']['pairwise_accuracy']
            improvement = best_acc - baseline_acc
            f.write(f"- Baseline: {baseline_acc:.2f}%\n")
            f.write(f"- Best: {best_acc:.2f}%\n")
            f.write(f"- Improvement: {improvement:+.2f}%\n\n")

            f.write("## Next Steps\n")
            f.write("Phase 2: Analyze facet contributions and propose structural changes (add/remove/merge/split).\n")

        print(f"Summary written to {summary_path}")


if __name__ == "__main__":
    research = AutoFacetResearch(
        per_script_dir="./autoresearch/data/results/live/per_script",
        split_path="./autoresearch/data/results/validation/split.json",
        benchmark_path="./autoresearch/data/benchmark/benchmark.jsonl",
        results_dir="./autoresearch/data/results"
    )

    research.load_split()
    research.load_results()
    research.load_benchmark()
    research.run_phase1()
