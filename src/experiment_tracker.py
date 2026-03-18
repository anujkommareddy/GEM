"""Track auto-research experiments and improvements."""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


class ExperimentTracker:
    """Track and log auto-research experiments."""

    def __init__(self, experiments_dir: Path):
        """
        Initialize tracker.

        Args:
            experiments_dir: Directory to store experiment logs
        """
        self.experiments_dir = Path(experiments_dir)
        self.experiments_dir.mkdir(parents=True, exist_ok=True)
        self.experiments_log = self.experiments_dir / "experiments.jsonl"
        self.summary_file = self.experiments_dir / "experiment_summary.json"

    def start_experiment(self, description: str, config_changes: Dict) -> Dict:
        """
        Start a new experiment.

        Args:
            description: What is being tested
            config_changes: Dict of config changes (e.g., {"singular_vision": 0.30})

        Returns:
            Experiment metadata
        """
        exp = {
            "id": self._timestamp_id(),
            "timestamp": datetime.utcnow().isoformat(),
            "description": description,
            "config_changes": config_changes,
            "status": "running",
        }
        return exp

    def log_result(
        self,
        exp: Dict,
        baseline_accuracy: float,
        new_accuracy: float,
        sample_size: int,
        full_dataset: bool = False,
    ) -> Dict:
        """
        Log experiment result.

        Args:
            exp: Experiment metadata
            baseline_accuracy: Baseline pairwise accuracy
            new_accuracy: New pairwise accuracy
            sample_size: Number of scripts evaluated
            full_dataset: Whether evaluated on full 909 or sample

        Returns:
            Updated experiment metadata
        """
        improvement = new_accuracy - baseline_accuracy
        keep = improvement > 0.0

        exp.update(
            {
                "status": "completed",
                "baseline_accuracy": baseline_accuracy,
                "new_accuracy": new_accuracy,
                "improvement": improvement,
                "improvement_pct": (improvement / baseline_accuracy * 100) if baseline_accuracy > 0 else 0,
                "sample_size": sample_size,
                "full_dataset": full_dataset,
                "decision": "KEEP" if keep else "REVERT",
                "completed_at": datetime.utcnow().isoformat(),
            }
        )

        # Append to log
        with open(self.experiments_log, "a") as f:
            f.write(json.dumps(exp) + "\n")

        return exp

    def get_all_experiments(self) -> List[Dict]:
        """Load all experiments from log."""
        experiments = []
        if self.experiments_log.exists():
            with open(self.experiments_log) as f:
                for line in f:
                    experiments.append(json.loads(line))
        return experiments

    def get_improvements(self) -> List[Dict]:
        """Get experiments that resulted in improvements."""
        exps = self.get_all_experiments()
        return [e for e in exps if e.get("decision") == "KEEP" and e.get("improvement", 0) > 0]

    def get_summary(self) -> Dict:
        """Generate summary of all experiments."""
        exps = self.get_all_experiments()
        improvements = self.get_improvements()

        summary = {
            "total_experiments": len(exps),
            "improvements_found": len(improvements),
            "total_improvement": sum(e.get("improvement", 0) for e in improvements),
            "experiments": [
                {
                    "id": e["id"],
                    "description": e["description"],
                    "baseline": e.get("baseline_accuracy"),
                    "new": e.get("new_accuracy"),
                    "improvement": e.get("improvement"),
                    "improvement_pct": e.get("improvement_pct"),
                    "decision": e.get("decision"),
                    "full_dataset": e.get("full_dataset"),
                }
                for e in exps
            ],
        }

        # Save summary
        with open(self.summary_file, "w") as f:
            json.dump(summary, f, indent=2)

        return summary

    def print_summary(self):
        """Print nicely formatted summary."""
        summary = self.get_summary()

        print("\n" + "=" * 70)
        print("AUTO-RESEARCH EXPERIMENT SUMMARY")
        print("=" * 70)
        print(f"Total experiments: {summary['total_experiments']}")
        print(f"Improvements found: {summary['improvements_found']}")
        print(f"Total improvement: {summary['total_improvement']:.4f} ({summary['total_improvement']*100:.2f}%)")
        print()

        if summary["experiments"]:
            print("EXPERIMENTS:")
            print("-" * 70)
            for exp in summary["experiments"]:
                status = "✅" if exp["decision"] == "KEEP" else "❌"
                print(
                    f"{status} {exp['id']:20} | {exp['description']:30} | "
                    f"{exp['baseline']:.3f} → {exp['new']:.3f} "
                    f"({exp['improvement']:+.4f}, {exp['improvement_pct']:+.2f}%)"
                )
            print()

        print("=" * 70)

    @staticmethod
    def _timestamp_id() -> str:
        """Generate timestamp-based ID."""
        return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
