"""Phase 6: Reporting.

Generates summary reports of the research findings.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from analyze import load_analyses
from factors import get_default_facets
from hypothesis import (
    compare_all_factors,
    find_misclassifications,
    test_stability,
)
from ingest import load_linked_dataset
from labels import build_default_schemes, inspect_labels, scheme_summary
from models import LabelScheme, LinkedRecord, PipelineReport, ScriptAnalysis


def generate_report(
    records: list[LinkedRecord],
    analyses: list[ScriptAnalysis],
    schemes: Optional[list[LabelScheme]] = None,
    output_dir: str = "output",
) -> PipelineReport:
    """Generate the full research report."""
    if schemes is None:
        schemes = build_default_schemes()

    os.makedirs(output_dir, exist_ok=True)

    # 1. Stability analysis
    stability = test_stability(records, analyses, schemes)
    stable_factors = [r.factor_name for r in stability if r.stable]
    unstable_factors = [r.factor_name for r in stability if not r.stable]

    # 2. Rank factors by usefulness
    factors_ranked = []
    for r in stability:
        factors_ranked.append({
            "factor": r.factor_name,
            "mean_separation": r.mean_separation,
            "std_separation": r.std_separation,
            "stable": r.stable,
            "direction_consistent": r.direction_consistent,
            "separations_by_scheme": r.separations,
        })

    # 3. Compare label schemes
    scheme_comparisons = []
    for scheme in schemes:
        comparisons = compare_all_factors(records, analyses, scheme)
        summary = scheme_summary(records, scheme)

        avg_separation = 0
        if comparisons:
            avg_separation = sum(abs(c.separation) for c in comparisons) / len(comparisons)

        scheme_comparisons.append({
            "scheme": scheme.name,
            "description": scheme.description,
            "winners": summary["winners"],
            "losers": summary["losers"],
            "excluded": summary["excluded"],
            "avg_factor_separation": round(avg_separation, 3),
            "factor_details": [c.model_dump() for c in comparisons],
        })

    # 4. Find best label scheme
    best_scheme = max(scheme_comparisons, key=lambda s: s["avg_factor_separation"])

    # 5. Generate recommendations
    recommendations = _generate_recommendations(
        stable_factors, unstable_factors, factors_ranked, best_scheme
    )

    report = PipelineReport(
        factors_ranked=factors_ranked,
        stable_factors=stable_factors,
        unstable_factors=unstable_factors,
        best_label_scheme=best_scheme["scheme"],
        scheme_comparisons=scheme_comparisons,
        recommendations=recommendations,
    )

    # Save outputs
    _save_report_json(report, output_dir)
    _save_report_text(report, records, analyses, schemes, output_dir)

    return report


def _generate_recommendations(
    stable: list[str],
    unstable: list[str],
    ranked: list[dict],
    best_scheme: dict,
) -> list[str]:
    """Generate actionable recommendations."""
    recs = []

    if stable:
        top = [f["factor"] for f in ranked if f["stable"]][:5]
        recs.append(
            f"INCLUDE in scoring rubric (stable, discriminating): {', '.join(top)}"
        )

    if unstable:
        recs.append(
            f"EXCLUDE or investigate further (unstable): {', '.join(unstable[:5])}"
        )

    recs.append(
        f"Best label scheme: '{best_scheme['scheme']}' "
        f"(avg separation: {best_scheme['avg_factor_separation']:.3f})"
    )

    # Check for factors where winners score lower
    reversed_factors = [
        f["factor"] for f in ranked
        if f["mean_separation"] < -0.3 and f["stable"]
    ]
    if reversed_factors:
        recs.append(
            f"Reversed factors (losers score higher — investigate): {', '.join(reversed_factors)}"
        )

    # Sample size warnings
    for sc in [best_scheme]:
        if sc["winners"] < 10 or sc["losers"] < 10:
            recs.append(
                f"WARNING: Small sample sizes in '{sc['scheme']}' "
                f"(W={sc['winners']}, L={sc['losers']}). Results may be unreliable."
            )

    return recs


def _save_report_json(report: PipelineReport, output_dir: str):
    path = os.path.join(output_dir, "report.json")
    with open(path, "w") as f:
        json.dump(report.model_dump(), f, indent=2)
    print(f"✓ Saved JSON report to {path}")


def _save_report_text(
    report: PipelineReport,
    records: list[LinkedRecord],
    analyses: list[ScriptAnalysis],
    schemes: list[LabelScheme],
    output_dir: str,
):
    """Generate a human-readable text report."""
    lines = []
    lines.append("=" * 70)
    lines.append("GEM RESEARCH REPORT — Script Facet Analysis")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 70)

    # Dataset summary
    lines.append("\n## DATASET SUMMARY")
    lines.append(f"Total shows: {len(records)}")
    lines.append(f"Shows with scripts: {sum(1 for r in records if r.scripts)}")
    lines.append(f"Analyses completed: {len(analyses)}")

    label_dist = inspect_labels(records)
    lines.append(f"Raw label distribution: {label_dist}")

    # Scheme comparison
    lines.append("\n## LABEL SCHEME COMPARISON")
    for sc in report.scheme_comparisons:
        lines.append(f"\n  ### {sc['scheme']}")
        lines.append(f"  {sc['description']}")
        lines.append(f"  Winners: {sc['winners']} | Losers: {sc['losers']} | Excluded: {sc['excluded']}")
        lines.append(f"  Average facet separation: {sc['avg_factor_separation']:.3f}")

    lines.append(f"\n  Best scheme: {report.best_label_scheme}")

    # Factor rankings
    lines.append("\n## FACET RANKINGS (by discriminating power)")
    lines.append(f"{'Facet':<45} {'Sep':>7} {'Stable':>8} {'Direction':>12}")
    lines.append("-" * 75)
    for f in report.factors_ranked:
        direction = "W > L" if f["mean_separation"] > 0 else "L > W"
        stable = "YES" if f["stable"] else "no"
        lines.append(
            f"  {f['factor']:<43} {f['mean_separation']:>+7.3f} {stable:>8} {direction:>12}"
        )

    # Recommendations
    lines.append("\n## RECOMMENDATIONS")
    for i, rec in enumerate(report.recommendations, 1):
        lines.append(f"  {i}. {rec}")

    # Stable factors detail
    if report.stable_factors:
        lines.append("\n## STABLE FACETS (recommended for scoring rubric)")
        for fname in report.stable_factors:
            factor_data = next((f for f in report.factors_ranked if f["factor"] == fname), None)
            if factor_data:
                lines.append(f"\n  {fname}")
                lines.append(f"    Mean separation: {factor_data['mean_separation']:+.3f}")
                for scheme, sep in factor_data.get("separations_by_scheme", {}).items():
                    lines.append(f"    {scheme}: {sep:+.3f}")

    # Unstable factors
    if report.unstable_factors:
        lines.append("\n## UNSTABLE FACETS (review needed)")
        for fname in report.unstable_factors:
            factor_data = next((f for f in report.factors_ranked if f["factor"] == fname), None)
            if factor_data:
                lines.append(f"\n  {fname}")
                lines.append(f"    Mean separation: {factor_data['mean_separation']:+.3f}")
                lines.append(f"    Direction consistent: {factor_data['direction_consistent']}")

    lines.append("\n" + "=" * 70)
    lines.append("END OF REPORT")

    text = "\n".join(lines)
    path = os.path.join(output_dir, "report.txt")
    with open(path, "w") as f:
        f.write(text)
    print(f"✓ Saved text report to {path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    dataset_path = sys.argv[1] if len(sys.argv) > 1 else "data/linked_dataset.json"
    analyses_dir = sys.argv[2] if len(sys.argv) > 2 else "output/analyses"
    output_dir = sys.argv[3] if len(sys.argv) > 3 else "output"

    records = load_linked_dataset(dataset_path)
    analyses = load_analyses(analyses_dir)

    print(f"Loaded {len(records)} records, {len(analyses)} analyses")
    report = generate_report(records, analyses, output_dir=output_dir)

    print("\n" + "=" * 40)
    print("RECOMMENDATIONS:")
    for r in report.recommendations:
        print(f"  → {r}")
