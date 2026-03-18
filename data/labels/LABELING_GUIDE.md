# GEM Label Guide

## The Three Buckets

| Label | Definition |
|-------|-----------|
| **winner** | Clear breakout / transcendent cultural success. Shows still talked about years later, defined a genre or era, or achieved lasting cultural footprint. |
| **middle** | Ambiguous. Includes: cult hits, respectable shows that didn't break through, niche critical darlings, shows with mixed outcomes, shows with limited data. |
| **loser** | Clear failure to break out. Cancelled quickly, forgotten, never found an audience, or outcome data confirms underperformance. |

## Why Three Buckets?

The original winner/loser binary was creating noise. Too many high-quality, well-regarded shows were labeled "loser" simply because they weren't in the curated winners list. This compressed the signal.

The `middle` bucket is a holding zone — it means "we're not sure, don't use this for training signal." The optimizer only uses winners and losers for pairwise comparisons, so middle shows don't affect accuracy calculations.

## Label Commands

```bash
# See label stats
python3 src/label_manager.py stats

# Review all flagged items (non-interactive printout)
python3 src/label_manager.py review-list

# Interactive review (goes through flagged items one by one)
python3 src/label_manager.py review

# Look up a specific show
python3 src/label_manager.py show sherlock

# Manually set a label
python3 src/label_manager.py set "Sherlock_1x01_-_A_Study_In_Scarlet" middle

# Add a brand new show
python3 src/label_manager.py add "my_new_show_101_pilot" "My New Show" winner

# Export labels for scoring pipeline
python3 src/label_manager.py export
```

## Currently Flagged for Review (50 shows)

These are either:
- **Losers scoring 8.40+** on the v2 rubric (strong signal the model thinks they're transcendent — possible mislabels)
- **Winners scoring below 7.5** (possible mislabels in the other direction)
- **Previously unlabeled** entries (defaulted to middle)

Run `python3 src/label_manager.py review-list` to see the full list.

## Label Version History

| Version | File | Description |
|---------|------|-------------|
| v1 | data/labels/labels_v1.jsonl | Original binary: winner / loser only. Preserved read-only. |
| v2 | data/labels/labels_v2.jsonl | Three-bucket: winner / middle / loser. Active version. |

## Notes

- The split file (`data/results/validation/v2_split.json`) was built on v1 labels. After significant v2 relabeling, consider regenerating the split to ensure the holdout still has enough winners.
- Holdout requires ~10+ winners to be statistically meaningful. Current holdout has 13 winners.
- Adding shows to `middle` from the winner/loser pool will reduce the winner/loser count available for training.
