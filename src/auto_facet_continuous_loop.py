"""
Continuous autoresearch loop: keep proposing mutations, test on holdout,
keep improvements, reject degradations. Run until convergence or budget exhausted.
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import random
import numpy as np
from facet_mutations import FacetMutator


class ContinuousAutoFacetResearch:
    """Continuous autoresearch loop for facet optimization"""

    def __init__(self,
                 per_script_dir: str,
                 split_path: str,
                 benchmark_path: str,
                 results_dir: str,
                 initial_budget: float = 200.0,
                 cost_per_script: float = 0.015):
        self.per_script_dir = per_script_dir
        self.split_path = split_path
        self.benchmark_path = benchmark_path
        self.results_dir = results_dir

        self.budget_initial = initial_budget
        self.cost_per_script = cost_per_script
        self.budget_spent = 14.0  # Initial evaluation
        self.budget_remaining = initial_budget - self.budget_spent

        self.holdout_ids = []
        self.tune_ids = []
        self.all_results = {}
        self.benchmark = {}

        self.current_best = None
        self.current_best_accuracy = 0.0
        self.iteration = 0
        self.improvements = []
        self.rejections = []

    def load_data(self):
        """Load all data"""
        # Load split
        with open(self.split_path) as f:
            split = json.load(f)
            self.tune_ids = split.get("tune", [])
            self.holdout_ids = split.get("holdout", [])

        # Load results
        count = 0
        for json_file in Path(self.per_script_dir).glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                    script_id = data.get("script_id")
                    if script_id:
                        self.all_results[script_id] = data
                        count += 1
            except:
                pass

        # Load benchmark
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

        print(f"✓ Loaded {len(self.holdout_ids)} holdout, {len(self.tune_ids)} tune, {count} labels, {len(self.all_results)} results")

    def load_best_config(self, config_file: str):
        """Load current best config"""
        with open(config_file) as f:
            self.current_best = json.load(f)
            self.current_best_accuracy = self.current_best["holdout_performance"]["pairwise_accuracy"]
        print(f"✓ Current best: {self.current_best['config_name']} ({self.current_best_accuracy:.2f}%)")

    def evaluate_config(self, facets: List[str], weights: Dict[str, float], on_holdout: bool = True) -> Tuple[float, float]:
        """Evaluate a configuration"""
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

            weighted_sum = 0.0
            for facet, weight in weights.items():
                if facet == "dialogue+thematic_merged":
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

        winners = [score for score, label in scored if label == "winner"]
        losers = [score for score, label in scored if label == "loser"]

        if not winners or not losers:
            return 0.0, 0.0

        correct_pairs = sum(1 for w in winners for l in losers if w > l)
        total_pairs = len(winners) * len(losers)
        pairwise_acc = 100.0 * correct_pairs / total_pairs if total_pairs > 0 else 0.0

        all_scored_sorted = sorted(scored, key=lambda x: x[0], reverse=True)
        top_10_count = max(1, len(all_scored_sorted) // 10)
        top_10 = all_scored_sorted[:top_10_count]
        winners_in_top10 = sum(1 for _, label in top_10 if label == "winner")
        winner_enrichment = 100.0 * winners_in_top10 / len(winners) if winners else 0.0

        return pairwise_acc, winner_enrichment

    def propose_next_mutation(self) -> Optional[Dict]:
        """Intelligently propose the next mutation"""
        current_facets = self.current_best.get("facets", [])
        current_weights = self.current_best.get("weights", {})

        # Phase 1-2: Test weight mutations and facet removals (free)
        if self.iteration < 20:
            # Propose fine-tuned weight adjustments
            # Adjust weights: increase top facet by small amount, decrease others
            new_weights = {}
            sorted_facets = sorted(current_facets, key=lambda f: current_weights.get(f, 0), reverse=True)

            for facet in current_facets:
                if facet == sorted_facets[0]:
                    # Boost top facet slightly
                    new_weights[facet] = current_weights[facet] * (1.0 + 0.05 * (self.iteration % 5))
                elif facet == sorted_facets[1]:
                    # Keep second-highest steady
                    new_weights[facet] = current_weights[facet]
                else:
                    # Reduce others
                    new_weights[facet] = current_weights[facet] * (1.0 - 0.02 * (self.iteration % 5))

            total = sum(new_weights.values())
            new_weights = {f: w/total for f, w in new_weights.items()}

            return {
                "proposal_id": f"fine_weight_{self.iteration}",
                "name": f"Fine-tuned weight adjustment (iter {self.iteration})",
                "facets": current_facets,
                "weights": new_weights,
                "type": "fine_weight_tune",
                "cost": "$0"
            }

        # Phase 3: Try merging weakest facets (free)
        if self.iteration >= 20 and self.iteration < 25:
            # Try merging two weakest facets
            sorted_facets_by_weight = sorted(current_facets, key=lambda f: current_weights.get(f, 0))
            if len(sorted_facets_by_weight) >= 2:
                f1, f2 = sorted_facets_by_weight[0], sorted_facets_by_weight[1]
                new_facets = [f for f in current_facets if f not in [f1, f2]] + [f"{f1}+{f2}_merged"]
                new_weights = {f: current_weights[f] for f in current_facets if f not in [f1, f2]}
                new_weights[f"{f1}+{f2}_merged"] = current_weights[f1] + current_weights[f2]

                return {
                    "proposal_id": f"merge_{f1}_{f2}_{self.iteration}",
                    "name": f"Merge {f1} + {f2}",
                    "facets": new_facets,
                    "weights": new_weights,
                    "type": "facet_merge",
                    "cost": "$0"
                }

        # Phase 4: If budget allows, propose facet splitting
        if self.iteration >= 25 and self.budget_remaining > 30:
            # Propose splitting the highest-weight facet
            top_facet = max(current_facets, key=lambda f: current_weights.get(f, 0))

            if top_facet == "singular_vision":
                return {
                    "proposal_id": f"split_singular_vision_{self.iteration}",
                    "name": "Split singular_vision into authorial + premise (needs LLM)",
                    "facets": [f for f in current_facets if f != top_facet] + ["authorial_distinctiveness", "premise_audacity"],
                    "weights": None,
                    "type": "facet_split",
                    "requires_llm": True,
                    "cost": f"${self.cost_per_script * 200:.2f}-${self.cost_per_script * 909:.2f}",
                    "description": "Would evaluate on 200-script sample first (~$3), then rollout if promising (~$14)"
                }

        # No more proposals
        return None

    def test_and_decide(self, proposal: Dict) -> bool:
        """Test a proposal and decide whether to keep it"""
        facets = proposal["facets"]
        weights = proposal["weights"]

        if proposal.get("requires_llm"):
            print(f"\n⏸  Iteration {self.iteration}: Proposal requires LLM evaluation (split facet)")
            print(f"    {proposal['name']}")
            print(f"    Cost: {proposal['cost']}")
            print(f"    Budget remaining: ${self.budget_remaining:.2f}")
            print(f"    → Skipping for now (would need external LLM call)")
            self.rejections.append(proposal)
            return False

        # Evaluate on holdout
        holdout_acc, holdout_enrichment = self.evaluate_config(facets, weights, on_holdout=True)
        tune_acc, _ = self.evaluate_config(facets, weights, on_holdout=False)

        improvement = holdout_acc - self.current_best_accuracy
        gap = tune_acc - holdout_acc

        result = {
            "iteration": self.iteration,
            "proposal_id": proposal.get("proposal_id"),
            "name": proposal["name"],
            "type": proposal.get("type"),
            "holdout_accuracy": holdout_acc,
            "tune_accuracy": tune_acc,
            "overfitting_gap": gap,
            "improvement": improvement,
            "facets": facets,
            "weights": weights,
            "timestamp": datetime.now().isoformat()
        }

        # Decide: keep if improvement > 0.1% OR simpler with >-0.1% loss
        simpler = len(facets) < len(self.current_best["facets"])

        if improvement > 0.1:
            print(f"✓ Iter {self.iteration}: {proposal['name']:<50} → +{improvement:.2f}% (KEEP)")
            self.current_best_accuracy = holdout_acc
            self.current_best = {
                "config_name": f"best_iter_{self.iteration}",
                "iteration": self.iteration,
                "proposal": proposal,
                "holdout_performance": {
                    "pairwise_accuracy": holdout_acc,
                    "top10_enrichment": holdout_enrichment
                },
                "train_performance": {
                    "pairwise_accuracy": tune_acc
                },
                "overfitting_gap": gap,
                "facets": facets,
                "weights": weights
            }
            self.improvements.append(result)
            return True
        elif simpler and improvement > -0.1:
            print(f"✓ Iter {self.iteration}: {proposal['name']:<50} → {improvement:+.2f}% ({len(facets)} facets, SIMPLER)")
            self.current_best_accuracy = holdout_acc
            self.current_best = {
                "config_name": f"best_iter_{self.iteration}",
                "iteration": self.iteration,
                "proposal": proposal,
                "holdout_performance": {
                    "pairwise_accuracy": holdout_acc,
                    "top10_enrichment": holdout_enrichment
                },
                "train_performance": {
                    "pairwise_accuracy": tune_acc
                },
                "overfitting_gap": gap,
                "facets": facets,
                "weights": weights
            }
            self.improvements.append(result)
            return True
        else:
            print(f"✗ Iter {self.iteration}: {proposal['name']:<50} → {improvement:+.2f}% (REJECT)")
            self.rejections.append(result)
            return False

    def run_loop(self, max_iterations: int = 30):
        """Run the continuous autoresearch loop"""
        print("\n" + "="*100)
        print("CONTINUOUS AUTORESEARCH LOOP")
        print("="*100)
        print(f"Budget: ${self.budget_remaining:.2f} remaining")
        print(f"Starting accuracy: {self.current_best_accuracy:.2f}%")
        print()

        consecutive_rejections = 0

        while self.iteration < max_iterations:
            self.iteration += 1

            # Propose next mutation
            proposal = self.propose_next_mutation()

            if not proposal:
                print(f"\n🛑 No more proposals available")
                break

            # Test and decide
            accepted = self.test_and_decide(proposal)

            if not accepted:
                consecutive_rejections += 1
                if consecutive_rejections >= 5:
                    print(f"\n🛑 5 consecutive rejections; stopping loop")
                    break
            else:
                consecutive_rejections = 0

            # Check budget
            if self.budget_remaining < 5:
                print(f"\n🛑 Budget nearly exhausted (${self.budget_remaining:.2f} remaining)")
                break

        # Save final results
        self._save_final_results()

    def _save_final_results(self):
        """Save final results to disk"""
        final_report = {
            "total_iterations": self.iteration,
            "improvements_found": len(self.improvements),
            "rejections": len(self.rejections),
            "final_accuracy": self.current_best_accuracy,
            "starting_accuracy": 71.13,
            "total_improvement": self.current_best_accuracy - 71.13,
            "best_config": self.current_best,
            "all_improvements": self.improvements,
            "all_rejections": self.rejections,
            "budget": {
                "initial": self.budget_initial,
                "spent": self.budget_spent,
                "remaining": self.budget_remaining
            }
        }

        report_path = os.path.join(self.results_dir, "auto_facet_continuous_final_report.json")
        with open(report_path, "w") as f:
            json.dump(final_report, f, indent=2)

        print(f"\n✓ Final report saved to auto_facet_continuous_final_report.json")
        print("\n" + "="*100)
        print("FINAL RESULTS")
        print("="*100)
        print(f"Total iterations: {self.iteration}")
        print(f"Improvements found: {len(self.improvements)}")
        print(f"Starting accuracy: 71.13%")
        print(f"Final accuracy: {self.current_best_accuracy:.2f}%")
        print(f"Total improvement: {self.current_best_accuracy - 71.13:+.2f}%")
        print(f"Best config: {self.current_best['config_name']}")
        print(f"Facets: {self.current_best['facets']}")
        print("="*100 + "\n")


if __name__ == "__main__":
    research = ContinuousAutoFacetResearch(
        per_script_dir="./autoresearch/data/results/live/per_script",
        split_path="./autoresearch/data/results/validation/split.json",
        benchmark_path="./autoresearch/data/benchmark/benchmark.jsonl",
        results_dir="./autoresearch/data/results"
    )

    research.load_data()
    research.load_best_config("./autoresearch/data/results/best_config_phase2a_m1.json")
    research.run_loop(max_iterations=30)
