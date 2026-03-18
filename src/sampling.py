"""Stratified sampling for faster iteration during auto-research."""

import json
from pathlib import Path
from typing import Set, List
import random


class StratifiedSampler:
    """Create representative samples maintaining winner/loser ratio."""

    def __init__(self, benchmark_file: Path, sample_size: int = 200):
        """
        Initialize sampler.

        Args:
            benchmark_file: Path to benchmark.jsonl
            sample_size: Total scripts to sample (default 200)
        """
        self.benchmark_file = benchmark_file
        self.sample_size = sample_size
        self.winners = []
        self.losers = []

        self._load_benchmark()

    def _load_benchmark(self):
        """Load benchmark and categorize by winner/loser."""
        with open(self.benchmark_file) as f:
            for line in f:
                data = json.loads(line)
                if data.get("label") == "winner":
                    self.winners.append(data["script_id"])
                elif data.get("label") == "loser":
                    self.losers.append(data["script_id"])

    def get_stratified_sample(self) -> Set[str]:
        """
        Get stratified sample maintaining winner/loser ratio.

        Returns:
            Set of script IDs to evaluate
        """
        # Maintain ratio: ~69 winners out of 901 = 7.7% winners
        # For 200 samples: ~15 winners, 185 losers
        num_winners = max(1, int(self.sample_size * (len(self.winners) / (len(self.winners) + len(self.losers)))))
        num_losers = self.sample_size - num_winners

        # Sample
        sampled_winners = set(random.sample(self.winners, min(num_winners, len(self.winners))))
        sampled_losers = set(random.sample(self.losers, min(num_losers, len(self.losers))))

        return sampled_winners | sampled_losers

    def get_balanced_sample(self, num_winners: int = 15) -> Set[str]:
        """
        Get explicitly balanced sample (useful for consistent experiments).

        Args:
            num_winners: Number of winners to sample

        Returns:
            Set of script IDs
        """
        num_losers = self.sample_size - num_winners
        sampled_winners = set(random.sample(self.winners, min(num_winners, len(self.winners))))
        sampled_losers = set(random.sample(self.losers, min(num_losers, len(self.losers))))

        return sampled_winners | sampled_losers

    def save_sample(self, sample_ids: Set[str], output_file: Path):
        """Save sample IDs to file for reproducibility."""
        with open(output_file, "w") as f:
            json.dump(sorted(list(sample_ids)), f, indent=2)

    def load_sample(self, sample_file: Path) -> Set[str]:
        """Load previously saved sample."""
        with open(sample_file) as f:
            return set(json.load(f))
