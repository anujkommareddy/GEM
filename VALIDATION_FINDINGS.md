# Holdout Validation Findings: Important Reality Check

**Date:** 2026-03-17
**Status:** ⚠️ CRITICAL OVERFITTING DETECTED

---

## Executive Summary

Our weight tuning achieved **81.92% pairwise accuracy on the training set**, but **only 71.23% on unseen holdout data**. This **13.4% gap indicates significant overfitting**. On closer inspection, the tuning provided almost **zero real improvement** on holdout data:

- **Baseline on holdout:** 71.13%
- **Tuned on holdout:** 71.23%
- **Actual gain:** +0.14% (essentially noise)

---

## What Happened

### The Problem: We Tuned on the Same Data We Evaluated On

We optimized weights across all 909 scripts, then reported results on those same 909. This is **data leakage** — we fit to our evaluation set.

### The Split

- **Tuning set:** 730 scripts (80%)
  - 56 winners, 674 losers
  - Used to find optimal weights

- **Holdout set:** 179 scripts (20%)
  - 13 winners, 166 losers
  - Never seen during tuning (true test)

---

## Results

| Metric | Tuning Set | Holdout Set | Gap | Interpretation |
|---|---|---|---|---|
| **Pairwise Accuracy** | 84.62% | 71.23% | -13.39% | ❌ Significant overfitting |
| **Winners in Top 10%** | 30.0% | 23.5% | -6.5 pp | ⚠️ Ranking still works but weaker |
| **Baseline Winner %** | 7.5% | 7.6% | N/A | Splits are balanced ✅ |

### Does It Generalize?

**❌ NO** — The 13.4% gap is too large. Industry standard is < 5% for generalization.

### Does Tuning Actually Help?

**⚠️ NOT REALLY** — Compared to baseline on holdout:
- Baseline: 71.13%
- Tuned: 71.23%
- **Gain: +0.14%** (within noise margin)

Winner ranking shows +15.9% lift (same as baseline), so no improvement there either.

### Do Winners Surface?

**✅ YES, PARTIALLY** — Winners appear in top 10% at 23.5% vs 7.6% baseline = **+15.9% lift**. But this lift matches the baseline too, so no additional gain from tuning.

---

## Why This Happened

### Root Cause: The Proposal Strategy Was Wrong

We proposed increasing high-gap dimensions (Singular Vision, Boldness, World Originality) but those returned **0.0% accuracy** in the tests. Looking back:

1. **High-gap proposals failed:** Trying to boost already-good predictors made things worse
2. **Low-gap proposals succeeded:** Decreasing Character Depth and Dialogue Language improved the metric
3. **But on holdout:** The decreases provided essentially zero benefit

### Why Did Low-Gap Reductions Work on Training Set?

Likely because:
- These dimensions had **noise** or **overfitting signal** in the training set
- By reducing their weight, we reduced the noise
- **But this noise didn't generalize** — the holdout set shows no improvement

---

## What This Means

### ❌ Current Config is NOT Production-Ready

- Holdout accuracy (71.23%) is acceptable but not exciting
- Tuning didn't actually improve performance
- No basis to claim our changes are better than baseline

### ⚠️ The Autoresearch Approach Needs Revision

The issue isn't the tool — it's the strategy:

1. **We tuned on all the data** instead of holding out a test set (done now!)
2. **We proposed changes without domain insight** (just blindly increasing/decreasing based on gaps)
3. **The gap analysis itself may be misleading** on the tuning set

### ✅ What We Learned

1. **Baseline weights are actually pretty good** (71% on unseen data)
2. **Winner ranking works** (15.9% lift over baseline)
3. **Need a different tuning strategy** that doesn't overfit

---

## Path Forward (Options)

### Option A: Accept Baseline (Conservative)
- **Revert to original weights**
- Use for product with 71% confidence (still 15.9% lift for winner ranking)
- Safe, no overfitting risk

### Option B: Start Over with Proper Holdout Approach (Recommended)
- **Freeze holdout set** (179 scripts — never touch again)
- **Use tuning set (730)** for all future optimization
- **Validate only on holdout** before shipping

- New strategy:
  1. Pick ONE dimension to tune at a time (more stable)
  2. Test on tuning set only
  3. Check holdout impact infrequently (to avoid overfitting to holdout)
  4. Stop tuning when holdout starts declining

### Option C: Build an Ensemble (Advanced)
- Combine multiple weight sets that work well
- Use voting or averaged scores
- May reduce overfitting risk

---

## Recommendation

**Option B** — Go back and retune properly with holdout validation:

1. Keep the holdout set frozen (don't look at it)
2. Design a more conservative tuning strategy
3. Validate on holdout occasionally
4. Expect final accuracy: **71-73% on holdout** (realistic goal)

This prevents overfitting and gives real confidence in results.

---

## Files Generated

- `data/results/validation/split.json` — 80/20 split (frozen)
- `data/results/validation/best_config_v1_validation.json` — Detailed metrics
- `data/results/validation/best_config_v1_validation.md` — This report
- `compare_baselines.py` — Script to compare baseline vs tuned

---

## Key Takeaway

**You made the right call asking for holdout validation.** This caught significant overfitting that would have been shipped. The good news: now we know the truth and can fix it properly.
