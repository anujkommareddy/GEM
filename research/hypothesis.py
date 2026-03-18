"""Hypothesis testing.

Compares facet patterns across winners and losers under different labeling schemes.
Identifies stable vs unstable facets.
"""

from __future__ import annotations

import json
import math
import os
from typing import Optional

from factors import get_facet_names
from labels import apply_scheme, build_default_schemes
from models import (
    FactorComparison,
    LabelScheme,
    LinkedRecord,
    ScriptAnalysis,
    StabilityResult,
)


# ---------------------------------------------------------------------------
# Factor comparison
# ---------------------------------------------------------------------------

def compare_factor(
    factor_name: str,
    winners: list[ScriptAnalysis],
    losers: list[ScriptAnalysis],
    scheme_name: str,
) -> Optional[FactorComparison]:
    """Compare a single facet between winner and loser groups."""
    winner_scores = _extract_scores(winners, factor_name)
    loser_scores = _extract_scores(losers, factor_name)

    if len(winner_scores) < 2 or len(loser_scores) < 2:
        return None

    w_mean = _mean(winner_scores)
    w_std = _std(winner_scores)
    l_mean = _mean(loser_scores)
    l_std = _std(loser_scores)

    # Cohen's d effect size
    pooled_std = math.sqrt(
        ((len(winner_scores) - 1) * w_std ** 2 + (len(loser_scores) - 1) * l_std ** 2)
        / (len(winner_scores) + len(loser_scores) - 2)
    )
    cohens_d = (w_mean - l_mean) / pooled_std if pooled_std > 0 else 0

    p_val = _welch_t_test(winner_scores, loser_scores)

    return FactorComparison(
        factor_name=factor_name,
        label_scheme=scheme_name,
        winner_mean=round(w_mean, 3),
        winner_std=round(w_std, 3),
        loser_mean=round(l_mean, 3),
        loser_std=round(l_std, 3),
        separation=round(cohens_d, 3),
        n_winners=len(winner_scores),
        n_losers=len(loser_scores),
        p_value=round(p_val, 4) if p_val is not None else None,
    )


def compare_all_factors(
    records: list[LinkedRecord],
    analyses: list[ScriptAnalysis],
    scheme: LabelScheme,
) -> list[FactorComparison]:
    """Compare all facets under a given labeling scheme."""
    winners_rec, losers_rec, _ = apply_scheme(records, scheme)

    analysis_map = {a.show_title.lower(): a for a in analyses}

    winner_analyses = [analysis_map[r.show.title.lower()] for r in winners_rec
                       if r.show.title.lower() in analysis_map]
    loser_analyses = [analysis_map[r.show.title.lower()] for r in losers_rec
                      if r.show.title.lower() in analysis_map]

    results = []
    for facet in get_facet_names():
        comp = compare_factor(facet, winner_analyses, loser_analyses, scheme.name)
        if comp:
            results.append(comp)

    return results


# ---------------------------------------------------------------------------
# Stability analysis
# ---------------------------------------------------------------------------

def test_stability(
    records: list[LinkedRecord],
    analyses: list[ScriptAnalysis],
    schemes: Optional[list[LabelScheme]] = None,
) -> list[StabilityResult]:
    """Test facet stability across multiple label schemes."""
    if schemes is None:
        schemes = build_default_schemes()

    all_comparisons: dict[str, dict[str, float]] = {}
    for scheme in schemes:
        comparisons = compare_all_factors(records, analyses, scheme)
        for comp in comparisons:
            if comp.factor_name not in all_comparisons:
                all_comparisons[comp.factor_name] = {}
            all_comparisons[comp.factor_name][scheme.name] = comp.separation

    results = []
    for factor_name, separations in all_comparisons.items():
        values = list(separations.values())
        mean_sep = _mean(values) if values else 0
        std_sep = _std(values) if len(values) > 1 else 0

        directions = [v > 0 for v in values if v != 0]
        direction_consistent = len(set(directions)) <= 1 if directions else False

        stable = (
            direction_consistent
            and abs(mean_sep) > 0.3
            and std_sep < abs(mean_sep) * 0.5
        )

        results.append(StabilityResult(
            factor_name=factor_name,
            schemes_tested=list(separations.keys()),
            separations=separations,
            mean_separation=round(mean_sep, 3),
            std_separation=round(std_sep, 3),
            stable=stable,
            direction_consistent=direction_consistent,
        ))

    results.sort(key=lambda r: abs(r.mean_separation), reverse=True)
    return results


# ---------------------------------------------------------------------------
# False positive / negative detection
# ---------------------------------------------------------------------------

def find_misclassifications(
    records: list[LinkedRecord],
    analyses: list[ScriptAnalysis],
    scheme: LabelScheme,
    stable_factors: list[str],
) -> dict:
    """Find shows that the facets would 'misclassify'."""
    winners_rec, losers_rec, _ = apply_scheme(records, scheme)
    analysis_map = {a.show_title.lower(): a for a in analyses}

    all_comparisons = compare_all_factors(records, analyses, scheme)
    factor_means = {}
    for comp in all_comparisons:
        if comp.factor_name in stable_factors:
            factor_means[comp.factor_name] = {
                "winner_mean": comp.winner_mean,
                "loser_mean": comp.loser_mean,
                "midpoint": (comp.winner_mean + comp.loser_mean) / 2,
            }

    false_negatives = []
    for r in winners_rec:
        analysis = analysis_map.get(r.show.title.lower())
        if not analysis:
            continue
        scores = analysis.all_scores_by_name()
        loser_like_count = sum(
            1 for f in stable_factors
            if f in scores and f in factor_means
            and scores[f] < factor_means[f]["midpoint"]
        )
        if loser_like_count > len(stable_factors) * 0.5:
            false_negatives.append({
                "show": r.show.title,
                "label": "winner",
                "loser_like_factors": loser_like_count,
                "total_stable_factors": len(stable_factors),
                "scores": {f: scores.get(f) for f in stable_factors},
            })

    false_positives = []
    for r in losers_rec:
        analysis = analysis_map.get(r.show.title.lower())
        if not analysis:
            continue
        scores = analysis.all_scores_by_name()
        winner_like_count = sum(
            1 for f in stable_factors
            if f in scores and f in factor_means
            and scores[f] >= factor_means[f]["midpoint"]
        )
        if winner_like_count > len(stable_factors) * 0.5:
            false_positives.append({
                "show": r.show.title,
                "label": "loser",
                "winner_like_factors": winner_like_count,
                "total_stable_factors": len(stable_factors),
                "scores": {f: scores.get(f) for f in stable_factors},
            })

    return {
        "false_negatives": false_negatives,
        "false_positives": false_positives,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_scores(analyses: list[ScriptAnalysis], factor_name: str) -> list[float]:
    """Extract scores for a given facet/factor name from analyses.

    Works with both new facet_scores and old factor_scores fields.
    """
    scores = []
    for a in analyses:
        # Try new facet_scores first
        for s in a.facet_scores:
            if s.facet_name == factor_name:
                scores.append(float(s.score))
                break
        else:
            # Fall back to old factor_scores
            for s in a.factor_scores:
                if s.factor_name == factor_name:
                    scores.append(float(s.score))
                    break
    return scores


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0
    m = _mean(values)
    return math.sqrt(sum((v - m) ** 2 for v in values) / (len(values) - 1))


def _welch_t_test(a: list[float], b: list[float]) -> Optional[float]:
    """Simple Welch's t-test. Returns p-value or None if can't compute."""
    if len(a) < 2 or len(b) < 2:
        return None

    ma, mb = _mean(a), _mean(b)
    sa, sb = _std(a), _std(b)
    na, nb = len(a), len(b)

    se = math.sqrt(sa ** 2 / na + sb ** 2 / nb)
    if se == 0:
        return None

    t_stat = (ma - mb) / se

    num = (sa ** 2 / na + sb ** 2 / nb) ** 2
    denom = (sa ** 2 / na) ** 2 / (na - 1) + (sb ** 2 / nb) ** 2 / (nb - 1)
    if denom == 0:
        return None
    df = num / denom

    z = abs(t_stat)
    if z > 6:
        return 0.0001
    p = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    p = 2 * p
    return min(p, 1.0)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    from analyze import load_analyses
    from ingest import load_linked_dataset

    dataset_path = sys.argv[1] if len(sys.argv) > 1 else "data/linked_dataset.json"
    analyses_dir = sys.argv[2] if len(sys.argv) > 2 else "output/analyses"

    records = load_linked_dataset(dataset_path)
    analyses = load_analyses(analyses_dir)

    print(f"Loaded {len(records)} records, {len(analyses)} analyses\n")

    schemes = build_default_schemes()
    stability = test_stability(records, analyses, schemes)

    print("Facet Stability Results:")
    print("=" * 70)
    for r in stability:
        status = "STABLE" if r.stable else "UNSTABLE"
        direction = "winners higher" if r.mean_separation > 0 else "losers higher"
        print(f"\n  {r.factor_name}: {status}")
        print(f"    Mean separation: {r.mean_separation:+.3f} ({direction})")
        print(f"    Std: {r.std_separation:.3f}")
        print(f"    Direction consistent: {r.direction_consistent}")
        for scheme, sep in r.separations.items():
            print(f"      {scheme}: {sep:+.3f}")

    stable_factors = [r.factor_name for r in stability if r.stable]
    print(f"\n\nStable facets ({len(stable_factors)}):")
    for f in stable_factors:
        print(f"  - {f}")
