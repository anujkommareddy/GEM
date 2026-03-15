"""Phase 2: Flexible labeling system.

Supports multiple winner/loser definitions to test factor stability.
Tuned for the actual GEM dataset which has binary "winner"/"loser" labels.
"""

from __future__ import annotations

import random
from typing import Optional

from models import LabelScheme, LinkedRecord, WinnerLabel


# ---------------------------------------------------------------------------
# Built-in label schemes
# ---------------------------------------------------------------------------

def build_default_schemes() -> list[LabelScheme]:
    """Create the default set of labeling schemes.

    Since our dataset has only "winner" and "loser" raw labels, we create
    meaningfully different schemes by varying inclusion criteria.
    """
    return [
        LabelScheme(
            name="binary_all",
            description="All labeled shows with scripts. Full winner vs loser comparison (52W vs 757L).",
            mapping={
                "winner": WinnerLabel.WINNER,
                "loser": WinnerLabel.LOSER,
            },
            exclude_ambiguous=False,
        ),
        LabelScheme(
            name="strict_confident",
            description="Only high-confidence filename matches (exact PDF filename link). Excludes fuzzy matches.",
            mapping={
                "winner": WinnerLabel.WINNER,
                "loser": WinnerLabel.LOSER,
            },
            exclude_ambiguous=False,
            # Applied via custom logic in apply_scheme_strict
        ),
        LabelScheme(
            name="balanced_sample",
            description="All winners vs a size-matched random sample of losers (52W vs ~52L) to control for class imbalance.",
            mapping={
                "winner": WinnerLabel.WINNER,
                "loser": WinnerLabel.LOSER,
            },
            exclude_ambiguous=False,
        ),
    ]


# ---------------------------------------------------------------------------
# Applying labels
# ---------------------------------------------------------------------------

def apply_scheme(
    records: list[LinkedRecord],
    scheme: LabelScheme,
) -> tuple[list[LinkedRecord], list[LinkedRecord], list[LinkedRecord]]:
    """Apply a label scheme and partition records into winners, losers, excluded.

    Only includes records that have scripts linked.
    Returns: (winners, losers, excluded)
    """
    winners, losers, excluded = [], [], []

    for record in records:
        if not record.scripts:
            excluded.append(record)
            continue

        # Strict confident: only filename-exact matches
        if scheme.name == "strict_confident" and record.match_method not in ("filename_exact", "filename_case_insensitive"):
            excluded.append(record)
            continue

        label = record.resolved_label(scheme)

        if label is None:
            excluded.append(record)
        elif label == WinnerLabel.AMBIGUOUS and scheme.exclude_ambiguous:
            excluded.append(record)
        elif label == WinnerLabel.WINNER:
            winners.append(record)
        elif label == WinnerLabel.LOSER:
            losers.append(record)
        else:
            excluded.append(record)

    # Balanced sample: downsample losers to match winner count
    if scheme.name == "balanced_sample" and winners and losers:
        n_winners = len(winners)
        if len(losers) > n_winners:
            random.seed(42)  # Reproducible
            losers = random.sample(losers, n_winners)
            excluded.extend([r for r in records if r.scripts and
                           r.resolved_label(scheme) == WinnerLabel.LOSER and
                           r not in losers])

    return winners, losers, excluded


# ---------------------------------------------------------------------------
# Scheme creation helpers
# ---------------------------------------------------------------------------

def create_scheme_from_raw_values(
    name: str,
    description: str,
    winner_values: list[str],
    loser_values: list[str],
    ambiguous_values: Optional[list[str]] = None,
    exclude_ambiguous: bool = False,
) -> LabelScheme:
    """Create a label scheme from explicit lists of raw values."""
    mapping = {}
    for v in winner_values:
        mapping[v.lower().strip()] = WinnerLabel.WINNER
    for v in loser_values:
        mapping[v.lower().strip()] = WinnerLabel.LOSER
    for v in (ambiguous_values or []):
        mapping[v.lower().strip()] = WinnerLabel.AMBIGUOUS

    return LabelScheme(
        name=name,
        description=description,
        mapping=mapping,
        exclude_ambiguous=exclude_ambiguous,
    )


# ---------------------------------------------------------------------------
# Inspection / diagnostics
# ---------------------------------------------------------------------------

def inspect_labels(records: list[LinkedRecord]) -> dict[str, int]:
    """Count raw label values across all records."""
    counts: dict[str, int] = {}
    for r in records:
        key = r.show.raw_label.strip().lower()
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def scheme_summary(
    records: list[LinkedRecord],
    scheme: LabelScheme,
) -> dict:
    """Show how a scheme partitions the data."""
    winners, losers, excluded = apply_scheme(records, scheme)
    total_with_scripts = sum(1 for r in records if r.scripts)
    return {
        "scheme": scheme.name,
        "description": scheme.description,
        "winners": len(winners),
        "losers": len(losers),
        "excluded": len(excluded),
        "total": len(records),
        "total_with_scripts": total_with_scripts,
        "winner_pct": round(len(winners) / max(total_with_scripts, 1) * 100, 1),
        "loser_pct": round(len(losers) / max(total_with_scripts, 1) * 100, 1),
    }
