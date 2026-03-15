"""Phase 2: Flexible labeling system.

Supports multiple winner/loser definitions to test factor stability.
"""

from __future__ import annotations

from typing import Optional

from models import LabelScheme, LinkedRecord, WinnerLabel


# ---------------------------------------------------------------------------
# Built-in label schemes
# ---------------------------------------------------------------------------

def build_default_schemes() -> list[LabelScheme]:
    """Create the default set of labeling schemes.

    These get refined once we see the actual data — the mappings below
    cover common patterns. Run `inspect_labels()` first to see what raw
    values exist in your sheet, then adjust or add schemes.
    """
    return [
        LabelScheme(
            name="binary_strict",
            description="Strict binary: only clear winners and clear losers. Excludes anything ambiguous.",
            mapping={
                "winner": WinnerLabel.WINNER,
                "loser": WinnerLabel.LOSER,
                "w": WinnerLabel.WINNER,
                "l": WinnerLabel.LOSER,
                "yes": WinnerLabel.WINNER,
                "no": WinnerLabel.LOSER,
                "hit": WinnerLabel.WINNER,
                "flop": WinnerLabel.LOSER,
                "success": WinnerLabel.WINNER,
                "failure": WinnerLabel.LOSER,
                "breakout": WinnerLabel.WINNER,
                # Anything else falls through as None (excluded)
            },
            exclude_ambiguous=True,
        ),
        LabelScheme(
            name="binary_broad",
            description="Broad binary: includes moderate successes as winners and moderate failures as losers.",
            mapping={
                "winner": WinnerLabel.WINNER,
                "loser": WinnerLabel.LOSER,
                "w": WinnerLabel.WINNER,
                "l": WinnerLabel.LOSER,
                "yes": WinnerLabel.WINNER,
                "no": WinnerLabel.LOSER,
                "hit": WinnerLabel.WINNER,
                "flop": WinnerLabel.LOSER,
                "success": WinnerLabel.WINNER,
                "failure": WinnerLabel.LOSER,
                "breakout": WinnerLabel.WINNER,
                "moderate": WinnerLabel.AMBIGUOUS,
                "mixed": WinnerLabel.AMBIGUOUS,
                "ok": WinnerLabel.AMBIGUOUS,
                "average": WinnerLabel.AMBIGUOUS,
                "mid": WinnerLabel.AMBIGUOUS,
            },
            exclude_ambiguous=False,
        ),
        LabelScheme(
            name="top_vs_bottom",
            description="Only top-tier winners vs bottom-tier losers. Middle ground excluded.",
            mapping={
                "breakout": WinnerLabel.WINNER,
                "hit": WinnerLabel.WINNER,
                "flop": WinnerLabel.LOSER,
                "failure": WinnerLabel.LOSER,
                "winner": WinnerLabel.AMBIGUOUS,
                "loser": WinnerLabel.AMBIGUOUS,
                "w": WinnerLabel.AMBIGUOUS,
                "l": WinnerLabel.AMBIGUOUS,
            },
            exclude_ambiguous=True,
        ),
    ]


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


def create_numeric_scheme(
    name: str,
    description: str,
    field_name: str,
    winner_threshold: float,
    loser_threshold: float,
    records: list[LinkedRecord],
) -> tuple[LabelScheme, list[LinkedRecord]]:
    """Create a scheme based on a numeric field (e.g., ratings, scores).

    Modifies records' raw_label to the numeric bucket, then returns a scheme.
    """
    modified = []
    for r in records:
        val_str = r.show.extra.get(field_name, "")
        try:
            val = float(val_str)
        except (ValueError, TypeError):
            r_copy = r.model_copy()
            r_copy.show = r.show.model_copy()
            r_copy.show.raw_label = "ambiguous"
            modified.append(r_copy)
            continue

        r_copy = r.model_copy()
        r_copy.show = r.show.model_copy()
        if val >= winner_threshold:
            r_copy.show.raw_label = "winner"
        elif val <= loser_threshold:
            r_copy.show.raw_label = "loser"
        else:
            r_copy.show.raw_label = "ambiguous"
        modified.append(r_copy)

    scheme = LabelScheme(
        name=name,
        description=description,
        mapping={
            "winner": WinnerLabel.WINNER,
            "loser": WinnerLabel.LOSER,
            "ambiguous": WinnerLabel.AMBIGUOUS,
        },
        exclude_ambiguous=True,
    )
    return scheme, modified


# ---------------------------------------------------------------------------
# Applying labels
# ---------------------------------------------------------------------------

def apply_scheme(
    records: list[LinkedRecord],
    scheme: LabelScheme,
) -> tuple[list[LinkedRecord], list[LinkedRecord], list[LinkedRecord]]:
    """Apply a label scheme and partition records into winners, losers, excluded.

    Returns: (winners, losers, excluded)
    """
    winners, losers, excluded = [], [], []

    for record in records:
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
            # AMBIGUOUS but not excluding
            excluded.append(record)

    return winners, losers, excluded


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
    return {
        "scheme": scheme.name,
        "description": scheme.description,
        "winners": len(winners),
        "losers": len(losers),
        "excluded": len(excluded),
        "total": len(records),
        "winner_pct": round(len(winners) / max(len(records), 1) * 100, 1),
        "loser_pct": round(len(losers) / max(len(records), 1) * 100, 1),
    }


if __name__ == "__main__":
    import json
    import sys

    from ingest import load_linked_dataset

    dataset_path = sys.argv[1] if len(sys.argv) > 1 else "data/linked_dataset.json"
    records = load_linked_dataset(dataset_path)

    print("Raw label distribution:")
    for label, count in inspect_labels(records).items():
        print(f"  {label}: {count}")

    print("\nScheme summaries:")
    for scheme in build_default_schemes():
        summary = scheme_summary(records, scheme)
        print(f"\n  {summary['scheme']}: {summary['description']}")
        print(f"    Winners: {summary['winners']} ({summary['winner_pct']}%)")
        print(f"    Losers:  {summary['losers']} ({summary['loser_pct']}%)")
        print(f"    Excluded: {summary['excluded']}")
