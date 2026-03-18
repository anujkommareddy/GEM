"""Research loop for iterative evaluator improvement."""

import json
import logging
import shutil
from pathlib import Path
from typing import Dict, List
from datetime import datetime
import hashlib

from config import Config
from ingestion import PDFIngester
from benchmark import Benchmark
from metrics import MetricsTracker
from live_output import LiveOutputWriter

logger = logging.getLogger(__name__)


class ResearchLoop:
    """Manage iterative research and improvement loop."""

    def __init__(self, config: Config):
        """
        Initialize research loop.

        Args:
            config: Config object
        """
        self.config = config
        self.metrics_tracker = MetricsTracker(config.get_path("results_log"))
        self.experiment_dir = config.get_path("experiment_dir")

    def setup_benchmark(self, pdf_source: Path = None, labels_csv: Path = None) -> Benchmark:
        """
        Set up benchmark dataset.

        Args:
            pdf_source: Path to PDF directory (defaults to config)
            labels_csv: Optional CSV file with labels

        Returns:
            Initialized Benchmark object
        """
        pdf_source = Path(pdf_source) if pdf_source else self.config.get_path("pdf_source")
        benchmark_path = self.config.get_path("benchmark_file")

        logger.info("Setting up benchmark...")

        # Ingest PDFs
        ingester = PDFIngester(pdf_source, self.config.get_path("extracted_text"))
        metadata = ingester.ingest_all(skip_existing=True)

        # Initialize benchmark
        benchmark = Benchmark(benchmark_path, self.config.get_path("extracted_text") / "metadata.jsonl")
        benchmark.add_from_metadata(metadata)

        # Load labels if provided
        if labels_csv and Path(labels_csv).exists():
            benchmark.add_labels_from_csv(Path(labels_csv))
            logger.info(f"Loaded labels from {labels_csv}")

        benchmark.save()

        stats = benchmark.get_stats()
        logger.info(f"Benchmark ready: {stats['total_entries']} scripts, {stats['labeled_entries']} labeled")

        return benchmark

    def run_evaluation(
        self, benchmark: Benchmark, script_ids: List[str] = None, model: str = None
    ) -> List[Dict]:
        """
        Run evaluations on benchmark with live output.

        Args:
            benchmark: Benchmark object
            script_ids: Specific scripts to evaluate (None = all)
            model: Model to use (defaults to config)

        Returns:
            List of evaluation results
        """
        model = model or self.config.get("models.default")
        from evaluator import ScreenplayEvaluator
        evaluator = ScreenplayEvaluator(self.config, model)

        ingester = PDFIngester(
            self.config.get_path("pdf_source"), self.config.get_path("extracted_text")
        )

        if script_ids is None:
            entries = benchmark.get_all_entries()
        else:
            entries = [benchmark.get_entry(sid) for sid in script_ids if benchmark.get_entry(sid)]

        # Filter to only evaluable scripts (those with extracted text)
        text_dir = self.config.get_path("extracted_text")
        evaluable_ids = {f.stem for f in text_dir.glob("*.txt")}
        entries = [e for e in entries if e.script_id in evaluable_ids]

        logger.info(f"Running evaluation on {len(entries)} evaluable scripts with {model}...")

        # Initialize live output writer
        live = LiveOutputWriter(
            output_dir=self.experiment_dir,
            model=self.config.get(f"models.{model}.model", model),
            run_id=self._timestamp_id(),
        )
        live.set_total_scripts(len(entries))

        # Check for already-completed scripts (resume support)
        per_script_dir = live.per_script_dir
        already_done = set()
        for f in per_script_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("status") == "success":
                    already_done.add(data.get("script_id"))
            except Exception:
                pass
        if already_done:
            logger.info(f"Resuming — skipping {len(already_done)} already-completed scripts")

        results = []
        for i, entry in enumerate(entries, 1):
            # Skip already-evaluated scripts
            if entry.script_id in already_done:
                logger.info(f"[{i}/{len(entries)}] {entry.script_id} — already done, skipping")
                continue

            logger.info(f"[{i}/{len(entries)}] {entry.script_id}...")
            script_text = ingester.get_script_text(entry.script_id)
            result = evaluator.evaluate(entry.script_id, script_text)
            results.append(result)

            # Write to disk immediately
            live.record_result(result, entry)

        # Final flush of all outputs
        live.finalize()

        return results

    def backup_config(self, backup_dir: Path = None) -> Path:
        """
        Backup current config before making changes.

        Args:
            backup_dir: Where to store backup (defaults to experiment_dir)

        Returns:
            Path to backup directory
        """
        backup_dir = Path(backup_dir) if backup_dir else self.experiment_dir / f"backup_{self._timestamp_id()}"
        backup_dir.mkdir(parents=True, exist_ok=True)

        # Copy config files
        config_source = self.config.config_dir
        for cfg_file in config_source.glob("*.json"):
            shutil.copy(cfg_file, backup_dir / cfg_file.name)
        for md_file in config_source.glob("*.md"):
            shutil.copy(md_file, backup_dir / md_file.name)

        logger.info(f"Backed up config to {backup_dir}")
        return backup_dir

    def restore_config(self, backup_dir: Path):
        """
        Restore config from backup.

        Args:
            backup_dir: Path to backup directory
        """
        if not backup_dir.exists():
            raise FileNotFoundError(f"Backup not found: {backup_dir}")

        config_target = self.config.config_dir
        for cfg_file in backup_dir.glob("*.json"):
            shutil.copy(cfg_file, config_target / cfg_file.name)
        for md_file in backup_dir.glob("*.md"):
            shutil.copy(md_file, config_target / md_file.name)

        logger.info(f"Restored config from {backup_dir}")

    def propose_experiment(self, description: str) -> Dict:
        """
        Start a new experiment proposal.

        Args:
            description: What is being changed and why

        Returns:
            Experiment metadata
        """
        exp_id = self._timestamp_id()
        exp = {
            "id": exp_id,
            "created_at": datetime.utcnow().isoformat(),
            "description": description,
            "config_backup": str(self.backup_config()),
            "status": "proposed",
        }

        return exp

    def save_experiment_metadata(self, exp: Dict, metadata_file: Path = None):
        """Save experiment metadata."""
        if metadata_file is None:
            metadata_file = self.experiment_dir / f"exp_{exp['id']}.json"

        with open(metadata_file, "w") as f:
            json.dump(exp, f, indent=2)

        return metadata_file

    def finalize_experiment(
        self,
        exp: Dict,
        results: List[Dict],
        keep: bool,
        notes: str = "",
        files_changed: List[str] = None,
    ) -> Dict:
        """
        Finalize an experiment.

        Args:
            exp: Experiment metadata
            results: Evaluation results
            keep: Whether to keep changes
            notes: Human notes
            files_changed: List of files that were modified

        Returns:
            Updated experiment metadata
        """
        from metrics import MetricsTracker

        metrics = MetricsTracker(self.config.get_path("results_log"))

        successful = [r for r in results if r.get("status") == "success"]
        files_changed = files_changed or ["evaluator_config.json", "rubric_prompt.md"]

        exp["status"] = "completed"
        exp["completed_at"] = datetime.utcnow().isoformat()
        exp["keep"] = keep
        exp["notes"] = notes
        exp["successful_evals"] = len(successful)
        exp["total_evals"] = len(results)

        # Log to results file
        metrics.log_experiment(
            experiment_id=exp["id"],
            model=self.config.get("models.default"),
            scripts_evaluated=len(successful),
            metrics={},
            files_changed=files_changed,
            keep_discard="keep" if keep else "discard",
            notes=notes,
        )

        # If discarding, restore backup
        if not keep:
            backup_path = Path(exp["config_backup"])
            if backup_path.exists():
                self.restore_config(backup_path)
                logger.info("Changes discarded. Config restored from backup.")

        return exp

    @staticmethod
    def _timestamp_id() -> str:
        """Generate a timestamp-based ID."""
        return datetime.utcnow().strftime("%Y%m%d_%H%M%S")
