"""Main iteration orchestrator for auto-research loop (weight optimization only)."""

import json
import logging
from pathlib import Path
from typing import Dict, Optional, Set, List

from config import Config
from sampling import StratifiedSampler
from experiment_tracker import ExperimentTracker
from auto_proposer import AutoProposer
from benchmark import Benchmark

logger = logging.getLogger(__name__)


class IterationOrchestrator:
    """Orchestrate auto-research iterations by re-weighting existing evaluations."""

    def __init__(self, config: Config):
        """
        Initialize orchestrator.

        Args:
            config: Config object
        """
        self.config = config
        self.tracker = ExperimentTracker(config.get_path("experiment_dir"))
        self.proposer = AutoProposer()
        self.benchmark = Benchmark(
            config.get_path("benchmark_file"), config.get_path("extracted_text") / "metadata.jsonl"
        )

        self.baseline_accuracy = 0.787  # From our 909/909 run
        self.sample_ids = None
        self.all_results = self._load_all_results()

    def _load_all_results(self) -> Dict[str, Dict]:
        """Load all per-script evaluation results."""
        results = {}
        per_script_dir = self.config.get_path("experiment_dir") / "live" / "per_script"

        if not per_script_dir.exists():
            logger.warning(f"No results directory: {per_script_dir}")
            return results

        for f in per_script_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("status") == "success":
                    script_id = data.get("script_id")
                    results[script_id] = data
            except Exception as e:
                logger.warning(f"Failed to load {f.name}: {e}")

        logger.info(f"Loaded {len(results)} evaluation results")
        return results

    def create_sample(self, sample_size: int = 200) -> Set[str]:
        """
        Create and save a stratified sample.

        Args:
            sample_size: Number of scripts to sample

        Returns:
            Set of script IDs
        """
        sampler = StratifiedSampler(self.config.get_path("benchmark_file"), sample_size)
        self.sample_ids = sampler.get_balanced_sample()

        # Save for reproducibility
        sample_file = self.config.get_path("experiment_dir") / "current_sample.json"
        sampler.save_sample(self.sample_ids, sample_file)

        logger.info(f"Created stratified sample: {len(self.sample_ids)} scripts")
        winners = len([s for s in self.sample_ids if self._is_winner(s)])
        losers = len(self.sample_ids) - winners
        logger.info(f"  Winners: {winners}, Losers: {losers}")

        return self.sample_ids

    def _is_winner(self, script_id: str) -> bool:
        """Check if script is a winner."""
        entry = self.benchmark.get_entry(script_id)
        return entry and entry.label == "winner"

    def run_iteration(self, proposal: Dict, sample_only: bool = True) -> Dict:
        """
        Run a single iteration by re-weighting existing evaluations.

        Args:
            proposal: Proposal dict (from AutoProposer)
            sample_only: If True, calculate on sample; if False, full dataset

        Returns:
            Updated experiment metadata
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"Testing: {self.proposer.proposal_to_string(proposal)}")
        logger.info(f"{'='*70}")

        # Start experiment
        exp = self.tracker.start_experiment(proposal["rationale"], proposal)

        # Select scripts to analyze
        scripts_to_use = self.sample_ids if (sample_only and self.sample_ids) else None

        # Calculate accuracy with new weights
        new_accuracy = self._calculate_accuracy_with_weights(proposal, scripts_to_use)

        # Log result
        exp = self.tracker.log_result(
            exp,
            self.baseline_accuracy,
            new_accuracy,
            len(scripts_to_use) if scripts_to_use else len(self.all_results),
            full_dataset=not sample_only,
        )

        # Decide
        if exp["decision"] == "KEEP":
            logger.info(f"✅ IMPROVEMENT: {self.baseline_accuracy:.3f} → {new_accuracy:.3f} (+{exp['improvement']:.4f})")
            self.baseline_accuracy = new_accuracy
            # Apply config change
            self._apply_proposal(proposal)
        else:
            logger.info(f"❌ NO IMPROVEMENT: {new_accuracy:.3f} (reverted)")

        return exp

    def _calculate_accuracy_with_weights(
        self, proposal: Dict, script_ids: Optional[Set[str]] = None
    ) -> float:
        """
        Calculate pairwise ranking accuracy with new weights.

        Args:
            proposal: Proposal with new weights
            script_ids: If provided, only use scripts in this set

        Returns:
            Pairwise accuracy (0-1)
        """
        # Extract new weights from proposal
        new_weights = self._extract_weights_from_proposal(proposal)

        # Re-aggregate scores using new weights
        scores = {}
        for script_id, result in self.all_results.items():
            if script_ids and script_id not in script_ids:
                continue

            # Get individual dimension scores from aggregated results
            dims = result.get("aggregated", {}).get("individual_scores", {})
            if not dims:
                continue

            # Re-calculate weighted average with new weights
            weighted_sum = 0
            weight_total = 0

            for dim, score in dims.items():
                weight = new_weights.get(dim, 0)
                if weight > 0 and score is not None:
                    weighted_sum += score * weight
                    weight_total += weight

            if weight_total > 0:
                scores[script_id] = weighted_sum / weight_total

        # Load labels
        labels = {}
        with open(self.config.get_path("benchmark_file")) as f:
            for line in f:
                data = json.loads(line)
                if script_ids is None or data["script_id"] in script_ids:
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

        accuracy = correct / total if total > 0 else 0
        logger.info(
            f"Pairwise accuracy ({len(winners)} winners, {len(losers)} losers): "
            f"{correct}/{total} = {accuracy:.3f}"
        )

        return accuracy

    def _extract_weights_from_proposal(self, proposal: Dict) -> Dict[str, float]:
        """Extract weight changes from proposal and create new weights dict."""
        new_weights = AutoProposer.BASELINE_WEIGHTS.copy()

        if proposal["type"] in ["weight_increase", "weight_decrease"]:
            dim = proposal["dimension"]
            new_weights[dim] = proposal["new_weight"]

        return new_weights

    def _apply_proposal(self, proposal: Dict):
        """Apply proposal to config files."""
        eval_config_file = self.config.config_dir / "evaluator_config.json"
        with open(eval_config_file) as f:
            eval_config = json.load(f)

        if proposal["type"] in ["weight_increase", "weight_decrease"]:
            eval_config[proposal["dimension"]] = proposal["new_weight"]

        with open(eval_config_file, "w") as f:
            json.dump(eval_config, f, indent=2)

        logger.info(f"Applied: {proposal['dimension']} = {proposal['new_weight']:.3f}")

    def run_improvement_loop(self, max_iterations: int = 1, sample_only: bool = True, auto: bool = False):
        """
        Run improvement loop.

        Args:
            max_iterations: Max proposals per run (default 1 for manual, ignored if auto=True)
            sample_only: If True, use samples for speed
            auto: If True, test all remaining proposals automatically until diminishing returns
        """
        logger.info(f"\nStarting auto-research improvement loop")
        logger.info(f"Baseline accuracy: {self.baseline_accuracy:.3f}")
        if auto:
            logger.info(f"Mode: AUTOMATIC (test all, stop at diminishing returns)")
        else:
            logger.info(f"Mode: MANUAL (test {max_iterations} per run)")
        logger.info(f"Approach: Re-weight existing evaluations (no LLM calls)")

        # Create sample if needed
        if sample_only and not self.sample_ids:
            self.create_sample()

        # Generate proposals
        proposals = self.proposer.generate_improvement_sequence()
        logger.info(f"\nGenerated {len(proposals)} total proposals:")
        for i, p in enumerate(proposals, 1):
            logger.info(f"  {i}. {p['dimension']:25} {p['current_weight']:.2f} → {p['new_weight']:.2f}")

        # Load experiment history
        exps = self.tracker.get_all_experiments()
        tested_dims = {
            e.get("config_changes", {}).get("dimension")
            for e in exps
            if e.get("status") == "completed"
        }

        if tested_dims:
            logger.info(f"\nAlready tested: {', '.join(sorted(tested_dims))}")

        # Find untested proposals
        untested = [p for p in proposals if p["dimension"] not in tested_dims]
        if not untested:
            logger.info("\n✅ All proposals have been tested!")
            self.tracker.print_summary()
            return

        # Auto mode: test all until diminishing returns
        if auto:
            logger.info(f"\nAUTO MODE: Testing {len(untested)} remaining proposals...")
            improvements_found = []
            consecutive_failures = 0

            for proposal in untested:
                logger.info(f"\n[{len(improvements_found) + 1}/{len(untested)}] {proposal['dimension']}...")

                exp = self.run_iteration(proposal, sample_only=False)  # Always use full for auto

                if exp["decision"] == "KEEP" and exp["improvement"] > 0.0001:
                    logger.info(f"✅ +{exp['improvement']:.4f}")
                    improvements_found.append(exp)
                    consecutive_failures = 0
                else:
                    logger.info(f"❌ No improvement")
                    consecutive_failures += 1

                # Stop if 2+ consecutive failures (diminishing returns)
                if consecutive_failures >= 2:
                    logger.info(f"\nDiminishing returns detected. Stopping.")
                    break

            # Final summary
            logger.info(f"\n{'='*70}")
            logger.info(f"AUTO MODE COMPLETE")
            logger.info(f"{'='*70}")
            logger.info(f"Improvements found: {len(improvements_found)}")
            logger.info(f"Total improvement: {sum(e['improvement'] for e in improvements_found):.4f}")
            logger.info(f"Final accuracy: {self.baseline_accuracy:.4f}")
            logger.info(f"\nOptimized config saved to: {self.config.config_dir}/evaluator_config.json")
            self.tracker.print_summary()
            logger.info(f"\n{'='*70}\n")

        # Manual mode: test one at a time
        else:
            logger.info(f"\nTesting next proposal ({len(untested)} untested remaining):")
            for i, proposal in enumerate(untested[:max_iterations], 1):
                logger.info(f"\n[{i}/{min(len(untested), max_iterations)}]")

                exp = self.run_iteration(proposal, sample_only=sample_only)

                if exp["decision"] == "KEEP" and exp["improvement"] > 0.0001:
                    logger.info(f"\n✅ IMPROVEMENT FOUND: +{exp['improvement']:.4f}")
                else:
                    logger.info(f"\n❌ No improvement")

            # Status
            logger.info(f"\n{'='*70}")
            logger.info(f"NEXT STEPS")
            logger.info(f"{'='*70}")
            logger.info(f"Completed: {len(tested_dims)} / {len(proposals)}")
            logger.info(f"Remaining: {len(untested) - max_iterations}")
            logger.info(f"\nTo test all remaining automatically:")
            logger.info(f"  python3 main.py iterate --auto")
            logger.info(f"\nTo test next one manually:")
            logger.info(f"  python3 main.py iterate")
            logger.info(f"\nTo see summary:")
            logger.info(f"  cat data/results/experiment_summary.json")
            logger.info(f"\n{'='*70}\n")
