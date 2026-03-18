# Holdout Validation Report

**Config:** best_config_v1
**Date:** 2026-03-17

---

## Pairwise Ranking Accuracy (THE KEY METRIC)

| Set | Accuracy | Winners/Losers | Pairs Correct |
|---|---|---|---|
| Tuning | 0.8462 | 53/645 | 28928/34185 |
| **Holdout** | **0.7123** | **13/158** | **1463/2054** |
| **Gap** | **0.1340** | | |

---

## Winner Ranking (Top 10%)

| Set | Winners in Top 10% | Pct | Baseline Winner % | Lift |
|---|---|---|---|---|
| Tuning | 21/70 | 30.0% | 7.5% | +22.5% |
| **Holdout** | **4/17** | **23.5%** | **7.6%** | **+15.9%** |

---

## Interpretation

No interpretation available

---

## Key Questions

1. **Does it generalize?**
   - Tuning/holdout gap: 0.1340
   - Answer: ❌ NO

2. **Do winners appear at the top?**
   - Holdout top 10% winner %: 23.5%
   - Baseline: 7.6%
   - Lift: +15.9%
   - Answer: ⚠️ MAYBE - Weak signal

3. **Ready to ship?**
   - Holdout pairwise accuracy: 0.7123 (71.23%)
   - Answer: ❌ NO - More tuning needed
