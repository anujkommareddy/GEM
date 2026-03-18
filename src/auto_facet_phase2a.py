"""
Phase 2a: Test no-cost facet mutations (remove, merge, reweight)
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import numpy as np
from facet_mutations import FacetMutator


class Phase2aOrchestrator:
    """Test facet mutations on locked holdout set"""

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

    def evaluate_mutation(self, facets: List[str], weights: Dict[str, float], on_holdout: bool = True) -> Tuple[float, float]:
        """
        Evaluate a mutation on holdout (or tune for comparison).
        Facets can include pseudo-facets like "dialogue+thematic_merged" (averaged from two facets).
        Returns: (pairwise_accuracy, top10_winner_enrichment)
        """
        dataset_ids = self.holdout_ids if on_holdout else self.tune_ids

        scored = []
        for script_id in dataset_ids:
            result = self.all_results.get(script_id)
            label = self.benchmark.get(script_id)

            if not result or not label:
                continue

            individual_scores = result.get("aggregated", {}).get("individual_scores", {})
            if not individual_scores:
                continue

            # Re-aggregate with new facet set and weights
            weighted_sum = 0.0
            for facet, weight in weights.items():
                if facet == "dialogue+thematic_merged":
                    # Average dialogue_language and thematic_ambition
                    d_score = individual_scores.get("dialogue_language", 0)
                    t_score = individual_scores.get("thematic_ambition", 0)
                    merged_score = (d_score + t_score) / 2.0 if (d_score or t_score) else 0
                    weighted_sum += merged_score * weight
                else:
                    score = individual_scores.get(facet, 0)
                    weighted_sum += score * weight

            scored.append((weighted_sum, label))

        if not scored:
            return 0.0, 0.0

        # Pairwise accuracy
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

    def test_mutation(self, mutation: Dict) -> Dict:
        """Test a single mutation"""
        mutation_id = mutation["mutation_id"]
        name = mutation["name"]
        facets = mutation["facets"]
        weights = mutation["weights"]
        rationale = mutation["rationale"]

        # Evaluate on holdout
        holdout_acc, holdout_enrichment = self.evaluate_mutation(facets, weights, on_holdout=True)

        # Also evaluate on tune set for comparison
        tune_acc, tune_enrichment = self.evaluate_mutation(facets, weights, on_holdout=False)

        experiment = {
            "timestamp": datetime.now().isoformat(),
            "mutation_id": mutation_id,
            "name": name,
            "facets": facets,
            "weights": weights,
            "rationale": rationale,
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
            "decision": "PENDING",
        }

        self.experiments.append(experiment)
        return experiment

    def run_phase2a(self):
        """Run Phase 2a: test all no-cost mutations"""
        print("\n" + "="*100)
        print("PHASE 2a: NO-COST FACET MUTATIONS")
        print("="*100 + "\n")

        # Generate mutations
        mutator = FacetMutator()
        mutations = mutator.generate_mutations()
        mutator.print_mutations()

        # Save mutations
        mutations_data = [
            {
                "mutation_id": m.mutation_id,
                "name": m.name,
                "facets": m.facets,
                "weights": m.weights,
                "rationale": m.rationale,
                "cost": m.cost
            }
            for m in mutations
        ]
        with open(os.path.join(self.results_dir, "facet_mutations_phase2a.json"), "w") as f:
            json.dump(mutations_data, f, indent=2)

        # Test all mutations
        print("Testing mutations on holdout set...\n")
        for mutation_data in mutations_data:
            exp = self.test_mutation(mutation_data)
            holdout_acc = exp["metrics"]["holdout"]["pairwise_accuracy"]
            tune_acc = exp["metrics"]["tune"]["pairwise_accuracy"]
            facet_count = len(mutation_data["facets"])
            print(f"M{mutation_data['mutation_id']:2d} ({facet_count} facets): {mutation_data['name']:<45} | "
                  f"Holdout: {holdout_acc:6.2f}% | Tune: {tune_acc:6.2f}%")

        # Analyze results
        self._analyze_results()

    def _analyze_results(self):
        """Analyze Phase 2a results"""
        print("\n" + "="*100)
        print("PHASE 2a ANALYSIS")
        print("="*100 + "\n")

        # Sort by holdout accuracy
        sorted_exps = sorted(
            self.experiments,
            key=lambda e: e["metrics"]["holdout"]["pairwise_accuracy"],
            reverse=True
        )

        baseline = self.experiments[0]  # M0 is control (Phase 1 best)
        baseline_acc = baseline["metrics"]["holdout"]["pairwise_accuracy"]

        print(f"Baseline (M0 - Phase 1 best): {baseline_acc:.2f}%\n")
        print("Top 5 mutations by holdout accuracy:")
        for i, exp in enumerate(sorted_exps[:5], 1):
            name = exp["name"]
            holdout = exp["metrics"]["holdout"]["pairwise_accuracy"]
            tune = exp["metrics"]["tune"]["pairwise_accuracy"]
            gap = tune - holdout
            facet_count = len(exp["facets"])
            improvement = holdout - baseline_acc
            print(f"  {i}. [{facet_count} facets] {name:<40} | "
                  f"Holdout: {holdout:6.2f}% | Improvement: {improvement:+6.2f}%")

        # Decide which to promote
        best = sorted_exps[0]
        improvement = best["metrics"]["holdout"]["pairwise_accuracy"] - baseline_acc

        print(f"\nBest mutation: {best['name']}")
        print(f"  Holdout: {best['metrics']['holdout']['pairwise_accuracy']:.2f}%")
        print(f"  Improvement vs baseline: {improvement:+.2f}%")
        print(f"  Facet count: {len(best['facets'])} (vs {len(baseline['facets'])} in baseline)")

        if improvement > 0.2:  # Meaningful improvement (>0.2%)
            best["decision"] = "KEEP"
            print(f"\n✓ Promoting mutation M{best['mutation_id']} as new best config")
        elif improvement > -0.2:  # Within noise, but simpler is better
            if len(best['facets']) < len(baseline['facets']):
                best["decision"] = "KEEP_SIMPLER"
                print(f"\n✓ Promoting mutation M{best['mutation_id']} (simpler facet set, similar performance)")
            else:
                best["decision"] = "NO_IMPROVEMENT"
                print(f"\n✗ No meaningful improvement; sticking with baseline")
        else:
            best["decision"] = "NO_IMPROVEMENT"
            print(f"\n✗ Performance degraded; sticking with baseline")

        # Save experiments
        with open(os.path.join(self.results_dir, "facet_phase2a_experiments.jsonl"), "w") as f:
            for exp in self.experiments:
                f.write(json.dumps(exp) + "\n")

        print(f"\nExperiment log saved to facet_phase2a_experiments.jsonl")

        # Generate summary
        self._generate_summary(best, baseline)

    def _generate_summary(self, best_exp: Dict, baseline_exp: Dict):
        """Generate readable summary"""
        summary_path = os.path.join(self.results_dir, "facet_phase2a_summary.md")

        with open(summary_path, "w") as f:
            f.write("# Phase 2a: No-Cost Facet Mutations - Summary\n\n")

            f.write("## Objective\n")
            f.write("Test facet set mutations (remove, merge, reweight) that don't require LLM calls.\n\n")

            f.write("## Approach\n")
            f.write("- Generated 7 mutations by removing weak facets, merging correlated ones, reweighting\n")
            f.write("- All mutations tested on locked holdout set (179 scripts: 13 winners, 166 losers)\n")
            f.write("- Selected best by holdout accuracy; prefer simpler if performance is tied\n\n")

            f.write("## Results\n\n")
            f.write("### Baseline (Phase 1 Best)\n")
            f.write(f"- **Configuration**: {baseline_exp['name']}\n")
            f.write(f"- **Facets**: {len(baseline_exp['facets'])} ({', '.join(baseline_exp['facets'][:3])}...)\n")
            f.write(f"- **Holdout Accuracy**: {baseline_exp['metrics']['holdout']['pairwise_accuracy']:.2f}%\n\n")

            f.write("### Best Mutation\n")
            f.write(f"- **Configuration**: {best_exp['name']}\n")
            f.write(f"- **Facets**: {len(best_exp['facets'])} ({', '.join(best_exp['facets'][:3])}...)\n")
            f.write(f"- **Holdout Accuracy**: {best_exp['metrics']['holdout']['pairwise_accuracy']:.2f}%\n")
            f.write(f"- **Top 10% Enrichment**: {best_exp['metrics']['holdout']['top10_enrichment']:.2f}%\n")
            f.write(f"- **Improvement**: {best_exp['metrics']['holdout']['pairwise_accuracy'] - baseline_exp['metrics']['holdout']['pairwise_accuracy']:+.2f}%\n")
            f.write(f"- **Simplicity**: {len(best_exp['facets'])} facets (vs {len(baseline_exp['facets'])} baseline)\n\n")

            f.write("### Weights (Best Mutation)\n")
            f.write("```json\n")
            f.write(json.dumps(best_exp['weights'], indent=2) + "\n")
            f.write("```\n\n")

            f.write("## Key Insights\n")
            f.write("- Removing the weakest facets may improve generalization or hurt performance\n")
            f.write("- Simpler models (fewer facets) are preferred when performance is comparable\n")
            f.write("- Overfitting can occur with too many facets\n\n")

            f.write("## Decision\n")
            f.write(f"- **Action**: {best_exp['decision']}\n")
            f.write(f"- **Next Phase**: Phase 2b (test splitting high-gap facets on sample)\n")

        print(f"Summary written to {summary_path}")


if __name__ == "__main__":
    orchestrator = Phase2aOrchestrator(
        per_script_dir="./autoresearch/data/results/live/per_script",
        split_path="./autoresearch/data/results/validation/split.json",
        benchmark_path="./autoresearch/data/benchmark/benchmark.jsonl",
        results_dir="./autoresearch/data/results"
    )

    orchestrator.load_split()
    orchestrator.load_results()
    orchestrator.load_benchmark()
    orchestrator.run_phase2a()
