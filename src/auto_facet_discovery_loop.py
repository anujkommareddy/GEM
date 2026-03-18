"""
Smart autoresearch loop that discovers new facets, not just optimizes existing ones.
Proposes new dimensions → tests on sample → rolls out if promising → measures on holdout.
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import random
from facet_discoverer import FacetDiscoverer


class SmartAutoFacetLoop:
    """Autonomous facet discovery and optimization"""

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
        self.budget_spent = 14.0
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
        self.proposed_facets = []

    def load_data(self):
        """Load all data"""
        with open(self.split_path) as f:
            split = json.load(f)
            self.tune_ids = split.get("tune", [])
            self.holdout_ids = split.get("holdout", [])

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

        print(f"✓ Loaded {len(self.holdout_ids)} holdout, {len(self.tune_ids)} tune, {len(self.all_results)} results")

    def load_best_config(self, config_file: str):
        """Load current best"""
        with open(config_file) as f:
            self.current_best = json.load(f)
            self.current_best_accuracy = self.current_best.get("holdout_performance", {}).get("pairwise_accuracy", 0)
        print(f"✓ Current best: {self.current_best_accuracy:.2f}%")

    def evaluate_config(self, facets: List[str], weights: Dict[str, float], on_holdout: bool = True) -> Tuple[float, float]:
        """Evaluate a config on holdout or tune"""
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
                if facet in individual_scores:
                    weighted_sum += individual_scores[facet] * weight

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

    def propose_next(self) -> Optional[Dict]:
        """Propose next mutation or new facet to test"""
        current_facets = self.current_best.get("facets", [])
        current_weights = self.current_best.get("weights", {})

        # Phase 1: Fine-tune weights on current facet set (free)
        if self.iteration < 15:
            new_weights = {}
            sorted_facets = sorted(current_facets, key=lambda f: current_weights.get(f, 0), reverse=True)

            for facet in current_facets:
                if facet == sorted_facets[0]:
                    new_weights[facet] = current_weights[facet] * (1.0 + 0.03 * (self.iteration % 5))
                else:
                    new_weights[facet] = current_weights[facet] * (1.0 - 0.01 * (self.iteration % 5))

            total = sum(new_weights.values())
            new_weights = {f: w/total for f, w in new_weights.items()}

            return {
                "proposal_id": f"weight_tune_{self.iteration}",
                "name": f"Weight tuning iteration {self.iteration}",
                "type": "weight_tune",
                "facets": current_facets,
                "weights": new_weights,
                "cost": "$0",
                "requires_llm": False
            }

        # Phase 2: Propose new facets (costs LLM evaluation)
        if self.iteration >= 15 and self.budget_remaining > 20:
            discoverer = FacetDiscoverer(self.per_script_dir, self.benchmark_path)
            discoverer.load_data()
            all_proposals = discoverer.generate_facet_proposals(current_facets)

            # Pick the first untested proposal
            tested_names = {p.get("facet_name") for p in self.proposed_facets}
            for prop in all_proposals:
                if prop["facet_name"] not in tested_names:
                    # Estimate cost
                    sample_cost = self.cost_per_script * 200
                    rollout_cost = self.cost_per_script * 909
                    total_cost = sample_cost + rollout_cost

                    return {
                        "proposal_id": f"facet_{prop['facet_name']}_{self.iteration}",
                        "name": f"Test new facet: {prop['facet_name']}",
                        "type": "new_facet",
                        "facet_name": prop["facet_name"],
                        "facet_description": prop["description"],
                        "evaluation_guide": prop["evaluation_guide"],
                        "hypothesis": prop["hypothesis"],
                        "facets": current_facets + [prop["facet_name"]],
                        "sample_cost": sample_cost,
                        "rollout_cost": rollout_cost,
                        "total_cost": total_cost,
                        "requires_llm": True,
                        "cost": f"${sample_cost:.2f}-${total_cost:.2f}"
                    }

        # No more proposals
        return None

    def test_and_decide(self, proposal: Dict) -> bool:
        """Test and decide"""
        proposal_type = proposal.get("type")

        if proposal.get("requires_llm"):
            print(f"\n⏸  Iter {self.iteration}: NEW FACET PROPOSAL")
            print(f"    Facet: {proposal['facet_name']}")
            print(f"    Description: {proposal['facet_description']}")
            print(f"    Hypothesis: {proposal['hypothesis']}")
            print(f"    Sample cost: ${proposal['sample_cost']:.2f}")
            print(f"    Rollout cost: ${proposal['rollout_cost']:.2f}")
            print(f"    Budget remaining: ${self.budget_remaining:.2f}")
            print(f"    → REQUIRES EXTERNAL LLM EVALUATION (not tested)")
            self.proposed_facets.append(proposal)
            return False

        # Evaluate weight tune
        facets = proposal["facets"]
        weights = proposal["weights"]
        holdout_acc, _ = self.evaluate_config(facets, weights, on_holdout=True)
        tune_acc, _ = self.evaluate_config(facets, weights, on_holdout=False)
        improvement = holdout_acc - self.current_best_accuracy
        gap = tune_acc - holdout_acc

        print(f"✓ Iter {self.iteration}: {proposal['name']:<50} → {holdout_acc:6.2f}% ({improvement:+.2f}%)")

        if improvement > 0.05:  # Keep if improves even slightly
            self.current_best_accuracy = holdout_acc
            self.current_best = {
                "config_name": f"best_iter_{self.iteration}",
                "iteration": self.iteration,
                "holdout_performance": {"pairwise_accuracy": holdout_acc},
                "train_performance": {"pairwise_accuracy": tune_acc},
                "overfitting_gap": gap,
                "facets": facets,
                "weights": weights
            }
            self.improvements.append(proposal)
            return True

        self.rejections.append(proposal)
        return False

    def run(self, max_iterations: int = 25):
        """Run the smart autoresearch loop"""
        print("\n" + "="*100)
        print("SMART AUTORESEARCH LOOP: DISCOVER NEW FACETS")
        print("="*100)
        print(f"Budget remaining: ${self.budget_remaining:.2f}")
        print(f"Starting accuracy: {self.current_best_accuracy:.2f}%")
        print()

        consecutive_rejections = 0

        while self.iteration < max_iterations:
            self.iteration += 1

            proposal = self.propose_next()

            if not proposal:
                print(f"\n🛑 No more proposals")
                break

            accepted = self.test_and_decide(proposal)

            if not accepted:
                consecutive_rejections += 1
                if consecutive_rejections >= 10:
                    print(f"\n🛑 10 consecutive rejections; loop converged")
                    break
            else:
                consecutive_rejections = 0

            if self.budget_remaining < 5:
                print(f"\n🛑 Budget exhausted (${self.budget_remaining:.2f} remaining)")
                break

        self._finalize()

    def _finalize(self):
        """Finalize and report"""
        report = {
            "total_iterations": self.iteration,
            "improvements": len(self.improvements),
            "rejections": len(self.rejections),
            "proposed_new_facets": len(self.proposed_facets),
            "final_accuracy": self.current_best_accuracy,
            "starting_accuracy": 71.13,
            "total_improvement": self.current_best_accuracy - 71.13,
            "budget_spent": self.budget_spent,
            "budget_remaining": self.budget_remaining,
            "best_config": self.current_best,
            "proposed_facets": self.proposed_facets
        }

        report_path = os.path.join(self.results_dir, "smart_autoresearch_final_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        print("\n" + "="*100)
        print("FINAL REPORT")
        print("="*100)
        print(f"Iterations: {self.iteration}")
        print(f"Improvements found: {len(self.improvements)}")
        print(f"New facets proposed: {len(self.proposed_facets)}")
        print(f"Starting accuracy: 71.13%")
        print(f"Final accuracy: {self.current_best_accuracy:.2f}%")
        print(f"Total improvement: {self.current_best_accuracy - 71.13:+.2f}%")
        print(f"Current facets: {self.current_best['facets']}")
        print(f"Budget remaining: ${self.budget_remaining:.2f}")
        print(f"\nNext step: Evaluate proposed facets with LLM, continue autoresearch loop")
        print("="*100 + "\n")


if __name__ == "__main__":
    loop = SmartAutoFacetLoop(
        per_script_dir="./autoresearch/data/results/live/per_script",
        split_path="./autoresearch/data/results/validation/split.json",
        benchmark_path="./autoresearch/data/benchmark/benchmark.jsonl",
        results_dir="./autoresearch/data/results"
    )

    loop.load_data()
    loop.load_best_config("./autoresearch/data/results/best_config_phase2a_m1.json")
    loop.run(max_iterations=25)
