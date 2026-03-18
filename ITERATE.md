# Auto-Research Improvement Loop

Fast, systematic iteration on rubric weights using sampling + validation.

## Overview

The improvement loop:
1. **Proposes** changes based on per-dimension gap analysis
2. **Evaluates** on a fast 200-script stratified sample
3. **Validates** promising changes on full 909 dataset
4. **Tracks** all experiments and improvements

## Quick Start

### Basic: Sample-based fast iteration (4-5x faster)

```bash
python3 main.py iterate --sample-size 200 --max-iterations 10
```

This will:
- Create a stratified sample of 200 scripts (maintains winner/loser ratio)
- Test up to 10 weight adjustment proposals
- Validate improvements on full dataset
- Track all experiments

### Full dataset: Slower but more accurate

```bash
python3 main.py iterate --full --max-iterations 5
```

## How It Works

### 1. Proposals

Based on per-dimension analysis from the latest summary:

```
Singular Vision:       +2.20 gap | Current: 25% → INCREASE
Boldness:              +1.98 gap | Current: 5%  → INCREASE
World Originality:     +1.92 gap | Current: 10% → REVIEW
...
Character Depth:       +1.60 gap | Current: 20% → MAYBE DECREASE
```

Proposals are ordered by impact potential: higher gap = better predictor.

### 2. Sampling Strategy

**Stratified sample of 200 scripts:**
- ~15 winners (proportional to 69/909 winners)
- ~185 losers
- Maintains signal while reducing API calls by 4-5x
- Takes ~3-5 minutes per evaluation vs. 20+ minutes for full dataset

### 3. Experiment Tracking

Each iteration logs:
```json
{
  "id": "20260317_120000",
  "description": "Increase singular_vision weight from 25% to 30%",
  "baseline_accuracy": 0.787,
  "new_accuracy": 0.792,
  "improvement": +0.005,
  "decision": "KEEP",
  "full_dataset": false
}
```

View results:

```bash
cat data/results/live/experiments/experiment_summary.json
```

### 4. Validation

Once an improvement is found on the sample, it's validated on full 909:

```
Sample: 78.7% → 79.0% (+0.3%) ✅ KEEP
Validating on full 909...
Full: 78.7% → 79.1% (+0.4%) ✅ IMPROVEMENT CONFIRMED
```

## Commands

### Run iteration loop (default: samples)

```bash
python3 main.py iterate
```

Options:
- `--sample-size N` — Override sample size (default 200)
- `--max-iterations N` — Max proposals to test (default 10)
- `--full` — Use all 909 scripts instead of samples

### Check experiment status

```bash
# Full summary
cat data/results/live/experiments/experiment_summary.json

# Latest summary with new baseline
cat data/results/live/latest_summary.md

# Detailed experiment log
cat data/results/live/experiments/experiments.jsonl
```

## What Gets Changed

Proposals modify `config/evaluator_config.json` weights:

```json
{
  "singular_vision": 0.30,        // Increased from 0.25
  "boldness": 0.08,               // Increased from 0.05
  "character_depth": 0.18,        // Decreased from 0.20
  ...
}
```

If an improvement is reverted, weights return to baseline.

## Expected Improvements

Starting baseline: **78.7% pairwise accuracy**

Based on dimension analysis, expected improvements:
- Singular Vision (high gap): +0.5% to +1.0%
- Boldness (high gap): +0.3% to +0.8%
- Character Depth adjustment: +0.1% to +0.5%

**Realistic target: 80-82% accuracy** after 5-10 improvements.

## Workflow

Recommended workflow for finding improvements:

```bash
# 1. Run sample-based iterations (fast)
python3 main.py iterate --max-iterations 10

# 2. Review results
cat data/results/live/experiments/experiment_summary.json

# 3. Once improvements found, validate on full dataset
python3 main.py iterate --full --max-iterations 3

# 4. Lock in best configuration
# (Done automatically — weights saved to config/)

# 5. Rebuild final summary
python3 rebuild_summary.py
```

## Troubleshooting

**"Could not load text for X"** — Ignore, script is skipped (no text file)

**Low improvement (+0.001% or less)** — Result of noise, naturally reverted

**API rate limits** — Sample-based loop is much faster; use `--sample-size 150` if needed

**Want to reset to baseline?** — Restore `config/evaluator_config.json` from backup or manually reset weights

## What's Next

After finding improvements:
1. Fine-tune individual dimensions
2. Test rubric changes (not just weights)
3. Build human feedback loop
4. Eventually productionize as API
