# Phase 2a: No-Cost Facet Mutations - Summary

## Objective
Test facet set mutations (remove, merge, reweight) that don't require LLM calls.

## Approach
- Generated 7 mutations by removing weak facets, merging correlated ones, reweighting
- All mutations tested on locked holdout set (179 scripts: 13 winners, 166 losers)
- Selected best by holdout accuracy; prefer simpler if performance is tied

## Results

### Baseline (Phase 1 Best)
- **Configuration**: Current best (Phase 1 - P8)
- **Facets**: 7 (singular_vision, boldness, world_originality...)
- **Holdout Accuracy**: 72.40%

### Best Mutation
- **Configuration**: Remove character_depth (6-facet)
- **Facets**: 6 (singular_vision, boldness, world_originality...)
- **Holdout Accuracy**: 72.49%
- **Top 10% Enrichment**: 30.77%
- **Improvement**: +0.10%
- **Simplicity**: 6 facets (vs 7 baseline)

### Weights (Best Mutation)
```json
{
  "singular_vision": 0.43118606850536084,
  "boldness": 0.20439967729838424,
  "world_originality": 0.1553689121109027,
  "emotional_specificity": 0.12355131901820415,
  "thematic_ambition": 0.05215840385331375,
  "dialogue_language": 0.033335619213834385
}
```

## Key Insights
- Removing the weakest facets may improve generalization or hurt performance
- Simpler models (fewer facets) are preferred when performance is comparable
- Overfitting can occur with too many facets

## Decision
- **Action**: KEEP_SIMPLER
- **Next Phase**: Phase 2b (test splitting high-gap facets on sample)
