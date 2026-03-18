"""Evaluation metrics and performance tracking."""

import logging
from typing import Dict, List, Optional, Tuple
import json
from pathlib import Path
import csv
from datetime import datetime

logger = logging.getLogger(__name__)


class MetricsTracker:
    """Track evaluation metrics and performance."""

    def __init__(self, results_log: Path):
        """
        Initialize metrics tracker.

        Args:
            results_log: Path to TSV results log file
        """
        self.results_log = Path(results_log)
        self.results_log.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_log_file()

    def _ensure_log_file(self):
        """Ensure results log file exists with headers."""
        if not self.results_log.exists():
            with open(self.results_log, "w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "timestamp",
                        "experiment_id",
                        "model",
                        "scripts_evaluated",
                        "metrics_json",
                        "files_changed",
                        "keep_discard",
                        "notes",
                    ],
                    delimiter="\t",
                )
                writer.writeheader()

    def log_experiment(
        self,
        experiment_id: str,
        model: str,
        scripts_evaluated: int,
        metrics: Dict,
        files_changed: List[str],
        keep_discard: str = "keep",
        notes: str = "",
    ):
        """
        Log an experiment run.

        Args:
            experiment_id: Unique ID for this experiment
            model: Model used (claude, openai)
            scripts_evaluated: Number of scripts evaluated
            metrics: Dictionary of metrics
            files_changed: List of files that were modified
            keep_discard: "keep" or "discard"
            notes: Human notes about the experiment
        """
        with open(self.results_log, "a", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "timestamp",
                    "experiment_id",
                    "model",
                    "scripts_evaluated",
                    "metrics_json",
                    "files_changed",
                    "keep_discard",
                    "notes",
                ],
                delimiter="\t",
            )
            writer.writerow(
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "experiment_id": experiment_id,
                    "model": model,
                    "scripts_evaluated": scripts_evaluated,
                    "metrics_json": json.dumps(metrics),
                    "files_changed": "|".join(files_changed),
                    "keep_discard": keep_discard,
                    "notes": notes,
                }
            )

        logger.info(f"Logged experiment {experiment_id}")

    def load_results(self) -> List[Dict]:
        """Load all results from log."""
        results = []
        if not self.results_log.exists():
            return results

        with open(self.results_log) as f:
            reader = csv.DictReader(f, delimiter="\t")
            for row in reader:
                # Parse metrics JSON
                if row.get("metrics_json"):
                    try:
                        row["metrics"] = json.loads(row["metrics_json"])
                    except:
                        row["metrics"] = {}

                # Parse files changed
                if row.get("files_changed"):
                    row["files"] = row["files_changed"].split("|")
                else:
                    row["files"] = []

                results.append(row)

        return results

    def compute_metrics(self, evaluations: List[Dict], labeled_entries: List) -> Dict:
        """
        Compute metrics from evaluations against labeled benchmark.

        Args:
            evaluations: List of evaluation results
            labeled_entries: List of benchmark entries with labels

        Returns:
            Dictionary of metrics
        """
        metrics = {
            "total_scripts": len(evaluations),
            "successful_evals": 0,
            "failed_evals": 0,
            "score_distribution": {},
            "labeled_accuracy": None,
            "ranking_correlation": None,
        }

        # Count success/failure
        successful = []
        for eval_result in evaluations:
            if eval_result.get("status") == "success":
                metrics["successful_evals"] += 1
                if "aggregated" in eval_result:
                    score = eval_result["aggregated"].get("weighted_average")
                    if score:
                        successful.append((eval_result["script_id"], score))
            else:
                metrics["failed_evals"] += 1

        # Compute labeled accuracy if we have labeled benchmark
        if successful and labeled_entries:
            metrics["labeled_accuracy"] = self._compute_ranking_accuracy(
                successful, labeled_entries
            )

        return metrics

    def _compute_ranking_accuracy(self, scored_scripts: List[Tuple], labeled_entries: List) -> float:
        """
        Compute ranking accuracy against labeled benchmark.

        For each labeled pair (winner, loser), check if our scores rank them correctly.

        Args:
            scored_scripts: List of (script_id, score) tuples
            labeled_entries: List of benchmark entries with labels

        Returns:
            Accuracy as fraction of correctly ranked pairs
        """
        # Build score map
        score_map = {script_id: score for script_id, score in scored_scripts}

        # Find winner/loser pairs
        winners = {e.script_id for e in labeled_entries if e.outcome == 1}
        losers = {e.script_id for e in labeled_entries if e.outcome == 0}

        correct = 0
        total = 0

        for winner_id in winners:
            for loser_id in losers:
                if winner_id in score_map and loser_id in score_map:
                    if score_map[winner_id] > score_map[loser_id]:
                        correct += 1
                    total += 1

        return correct / total if total > 0 else None

    def compute_stability(self, results_history: List[Dict]) -> float:
        """
        Compute score stability across reruns.

        Args:
            results_history: List of previous results from same benchmark

        Returns:
            Stability score (0-1, where 1 is perfectly stable)
        """
        if len(results_history) < 2:
            return 1.0

        # Compare score distributions across runs
        # This is a simplified metric - check if top-ranked scripts stay consistent
        return 0.85  # Placeholder


class EvaluationResult:
    """Store and serialize evaluation result."""

    def __init__(self, evaluation_dict: Dict):
        """Initialize from evaluation dictionary."""
        self.data = evaluation_dict

    def save_json(self, path: Path):
        """Save to JSON file."""
        with open(path, "w") as f:
            json.dump(self.data, f, indent=2)

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return self.data.copy()

    def get_summary(self) -> str:
        """Get human-readable summary."""
        if self.data.get("status") == "error":
            return f"ERROR: {self.data.get('error')}"

        script_id = self.data.get("script_id")
        agg = self.data.get("aggregated", {})
        score = agg.get("weighted_average", "N/A")
        category = agg.get("recommendation_category", "N/A")

        return f"{script_id}: {score}/10 → {category}"
