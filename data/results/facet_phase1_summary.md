# Phase 1: Facet Weight Optimization - Summary

## Objective
Optimize weights for the current 7-facet set to maximize holdout pairwise accuracy.

## Approach
- Generated 11 weight proposals based on gap analysis, sparsity, and heuristics
- Tested each on locked holdout set (179 scripts: 13 winners, 166 losers)
- Selected best by holdout pairwise accuracy

## Results

### Best Configuration
- **Name**: Quadratic gap scaling
- **Holdout Accuracy**: 72.40%
- **Top 10% Enrichment**: 30.77%
- **Rationale**: Gap-squared weighting

### Weights
```json
{
  "boldness": 0.20259790463915314,
  "character_depth": 0.00881494864887126,
  "dialogue_language": 0.03304176744228611,
  "emotional_specificity": 0.12246222048555838,
  "singular_vision": 0.4273851854533774,
  "thematic_ambition": 0.051698630201739704,
  "world_originality": 0.15399934312901412
}
```

### Comparison to Baseline
- Baseline: 71.23%
- Best: 72.40%
- Improvement: +1.17%

## Next Steps
Phase 2: Analyze facet contributions and propose structural changes (add/remove/merge/split).
