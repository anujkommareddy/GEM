"""Benchmark dataset management and label handling."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkEntry:
    """A single benchmark entry."""

    script_id: str
    title: Optional[str] = None
    extracted_text_path: Optional[str] = None
    label: Optional[str] = None  # optioned, produced, contest_placement, etc.
    outcome: Optional[int] = None  # 0=pass, 1=recommend, etc.
    human_score: Optional[float] = None  # human evaluator score if available
    notes: Optional[str] = None
    metadata: Optional[Dict] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)


class Benchmark:
    """Manage benchmark dataset and labels."""

    def __init__(self, benchmark_file: Path, metadata_source: Path = None):
        """
        Initialize benchmark.

        Args:
            benchmark_file: Path to benchmark JSONL file
            metadata_source: Path to ingestion metadata.jsonl (optional)
        """
        self.benchmark_file = Path(benchmark_file)
        self.benchmark_file.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_source = Path(metadata_source) if metadata_source else None

        self.entries: Dict[str, BenchmarkEntry] = {}
        self._load_benchmark()

    def _load_benchmark(self):
        """Load existing benchmark file."""
        if not self.benchmark_file.exists():
            logger.info(f"Creating new benchmark file: {self.benchmark_file}")
            return

        with open(self.benchmark_file) as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    script_id = data.pop("script_id")
                    # Filter to only known fields
                    valid_fields = {f.name for f in BenchmarkEntry.__dataclass_fields__.values()}
                    filtered = {k: v for k, v in data.items() if k in valid_fields}
                    self.entries[script_id] = BenchmarkEntry(script_id=script_id, **filtered)

        logger.info(f"Loaded {len(self.entries)} benchmark entries")

    def add_from_metadata(self, metadata_list: List[Dict]):
        """
        Initialize benchmark from ingestion metadata.

        Args:
            metadata_list: List of metadata dicts from ingestion
        """
        for meta in metadata_list:
            script_id = meta["script_id"]
            if script_id not in self.entries:
                self.entries[script_id] = BenchmarkEntry(
                    script_id=script_id,
                    title=meta.get("detected_title"),
                    extracted_text_path=meta.get("extracted_text_path"),
                    metadata=meta,
                )
                logger.debug(f"Added {script_id} to benchmark")

    def add_labels_from_csv(self, csv_path: Path):
        """
        Load labels from CSV file.

        Expected columns: script_id, label, outcome, human_score, notes

        Args:
            csv_path: Path to CSV file with labels
        """
        import csv

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                script_id = row.get("script_id")
                if not script_id:
                    continue

                if script_id not in self.entries:
                    self.entries[script_id] = BenchmarkEntry(script_id=script_id)

                entry = self.entries[script_id]
                entry.label = row.get("label")
                entry.outcome = int(row["outcome"]) if row.get("outcome") else None
                entry.human_score = float(row["human_score"]) if row.get("human_score") else None
                entry.notes = row.get("notes")

        logger.info(f"Loaded labels from {csv_path}")

    def add_labels_from_jsonl(self, jsonl_path: Path):
        """
        Load labels from JSONL file.

        Each line should be: {"script_id": "...", "label": "...", ...}

        Args:
            jsonl_path: Path to JSONL file with labels
        """
        with open(jsonl_path) as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                script_id = data.pop("script_id")

                if script_id not in self.entries:
                    self.entries[script_id] = BenchmarkEntry(script_id=script_id)

                for key, value in data.items():
                    setattr(self.entries[script_id], key, value)

        logger.info(f"Loaded labels from {jsonl_path}")

    def get_entry(self, script_id: str) -> Optional[BenchmarkEntry]:
        """Get benchmark entry by script ID."""
        return self.entries.get(script_id)

    def get_labeled_entries(self) -> List[BenchmarkEntry]:
        """Get only entries with labels."""
        return [e for e in self.entries.values() if e.label is not None or e.outcome is not None]

    def get_unlabeled_entries(self) -> List[BenchmarkEntry]:
        """Get only entries without labels."""
        return [e for e in self.entries.values() if e.label is None and e.outcome is None]

    def get_all_entries(self) -> List[BenchmarkEntry]:
        """Get all benchmark entries."""
        return list(self.entries.values())

    def save(self):
        """Save benchmark to file."""
        with open(self.benchmark_file, "w") as f:
            for entry in sorted(self.entries.values(), key=lambda e: e.script_id):
                f.write(json.dumps(entry.to_dict()) + "\n")

        logger.info(f"Saved {len(self.entries)} entries to {self.benchmark_file}")

    def get_stats(self) -> Dict:
        """Get benchmark statistics."""
        all_entries = self.get_all_entries()
        labeled = self.get_labeled_entries()
        unlabeled = self.get_unlabeled_entries()

        labeled_with_scores = [e for e in labeled if e.human_score is not None]

        return {
            "total_entries": len(all_entries),
            "labeled_entries": len(labeled),
            "unlabeled_entries": len(unlabeled),
            "entries_with_human_scores": len(labeled_with_scores),
            "labeling_completeness": len(labeled) / len(all_entries) if all_entries else 0,
            "label_distribution": self._get_label_distribution(),
        }

    def _get_label_distribution(self) -> Dict[str, int]:
        """Get count of each label."""
        dist = {}
        for entry in self.entries.values():
            if entry.label:
                dist[entry.label] = dist.get(entry.label, 0) + 1
        return dist

    def create_train_test_split(self, test_fraction: float = 0.2, seed: int = 42) -> tuple:
        """
        Create random train/test split of labeled entries.

        Args:
            test_fraction: Fraction for test set
            seed: Random seed for reproducibility

        Returns:
            (train_entries, test_entries)
        """
        import random

        random.seed(seed)
        labeled = self.get_labeled_entries()
        test_count = max(1, int(len(labeled) * test_fraction))

        test_entries = random.sample(labeled, test_count)
        test_ids = {e.script_id for e in test_entries}
        train_entries = [e for e in labeled if e.script_id not in test_ids]

        return train_entries, test_entries
