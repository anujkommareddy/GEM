"""
Analyze current facet set performance to guide intelligent proposals.
"""
import json
import os
from pathlib import Path
from collections import defaultdict
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Tuple

@dataclass
class FacetMetrics:
    """Metrics for a single facet"""
    facet_name: str
    winner_avg: float
    loser_avg: float
    gap: float  # winner_avg - loser_avg
    gap_percentile: float  # where this ranks among all facets
    std_dev_overall: float


class FacetAnalyzer:
    """Analyze facet performance on current results"""

    def __init__(self, per_script_dir: str, benchmark_path: str):
        self.per_script_dir = per_script_dir
        self.benchmark_path = benchmark_path
        self.results = {}
        self.benchmark = {}

    def load_all_results(self) -> int:
        """Load all per_script JSON files"""
        count = 0
        for json_file in Path(self.per_script_dir).glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                    script_id = data.get("script_id")
                    if script_id:
                        self.results[script_id] = data
                        count += 1
            except Exception as e:
                print(f"Error loading {json_file}: {e}")
        print(f"Loaded {count} evaluated scripts")
        return count

    def load_benchmark(self) -> int:
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
        return count

    def analyze_facets(self) -> Dict[str, FacetMetrics]:
        """Analyze each facet: gap, std dev, percentile"""
        # Collect facet scores by label
        winner_scores = defaultdict(list)
        loser_scores = defaultdict(list)

        for script_id, result in self.results.items():
            label = self.benchmark.get(script_id)
            scores = result.get("aggregated", {}).get("individual_scores", {})

            if not label or not scores:
                continue

            for facet, score in scores.items():
                if label == "winner":
                    winner_scores[facet].append(score)
                else:
                    loser_scores[facet].append(score)

        # Compute metrics
        metrics = {}
        all_gaps = []

        for facet in sorted(winner_scores.keys()):
            w_scores = winner_scores.get(facet, [])
            l_scores = loser_scores.get(facet, [])

            if not w_scores or not l_scores:
                continue

            w_avg = np.mean(w_scores)
            l_avg = np.mean(l_scores)
            gap = w_avg - l_avg
            all_gaps.append(gap)

            # Overall std dev
            all_scores = w_scores + l_scores
            std_dev = np.std(all_scores)

            metrics[facet] = FacetMetrics(
                facet_name=facet,
                winner_avg=w_avg,
                loser_avg=l_avg,
                gap=gap,
                gap_percentile=0.0,  # Will fill in next
                std_dev_overall=std_dev
            )

        # Compute percentiles
        sorted_gaps = sorted(all_gaps)
        for facet, m in metrics.items():
            percentile = (sorted_gaps.index(m.gap) + 1) / len(sorted_gaps) * 100
            metrics[facet].gap_percentile = percentile

        return metrics

    def print_analysis(self, metrics: Dict[str, FacetMetrics]):
        """Print analysis results"""
        print("\n" + "="*80)
        print("FACET PERFORMANCE ANALYSIS")
        print("="*80)
        print(f"{'Facet':<25} {'Winner':>8} {'Loser':>8} {'Gap':>8} {'Percentile':>12} {'StdDev':>8}")
        print("-"*80)

        for facet in sorted(metrics.keys(), key=lambda f: metrics[f].gap, reverse=True):
            m = metrics[facet]
            print(f"{m.facet_name:<25} {m.winner_avg:>8.2f} {m.loser_avg:>8.2f} {m.gap:>8.2f} {m.gap_percentile:>11.1f}% {m.std_dev_overall:>8.2f}")

        print("\nKey insights:")
        high_gap = [m for m in metrics.values() if m.gap_percentile >= 75]
        low_gap = [m for m in metrics.values() if m.gap_percentile <= 25]
        print(f"  High-gap facets (top 25%): {[m.facet_name for m in high_gap]}")
        print(f"  Low-gap facets (bottom 25%): {[m.facet_name for m in low_gap]}")
        print("="*80 + "\n")


if __name__ == "__main__":
    analyzer = FacetAnalyzer(
        per_script_dir="./autoresearch/data/results/live/per_script",
        benchmark_path="./autoresearch/data/benchmark/benchmark.jsonl"
    )

    analyzer.load_all_results()
    analyzer.load_benchmark()
    metrics = analyzer.analyze_facets()
    analyzer.print_analysis(metrics)

    # Save for proposer to use
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
    with open("./autoresearch/data/results/facet_analysis.json", "w") as f:
        json.dump(metrics_dict, f, indent=2)
    print("Saved facet analysis to facet_analysis.json")
