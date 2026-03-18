# GEM Autoresearch Operating Manual

This document defines how to use the GEM autoresearch system for iteratively improving screenplay evaluation.

## Philosophy

This system is designed for **controlled, reproducible research** on screenplay evaluation. The key principles are:

1. **Fixed benchmark** — All evaluation metrics are measured against a fixed, labeled dataset
2. **Narrow editable surface** — Only specific files can be modified during research
3. **Full traceability** — Every experiment is logged with metadata and can be reproduced
4. **Simplicity over cleverness** — Code should be inspectable and maintainable
5. **Local-first** — Everything runs locally; no external services except LLMs

---

## Immutable Files

These files define the core system and **MUST NOT be modified** during research:

- `src/config.py` — Configuration loader
- `src/ingestion.py` — PDF ingestion and text extraction
- `src/benchmark.py` — Benchmark dataset management
- `src/evaluator.py` — Screenplay evaluator base
- `src/metrics.py` — Metrics computation
- `src/research_loop.py` — Research loop orchestration
- `src/cli.py` — Command-line interface
- `data/benchmark/benchmark.jsonl` — Benchmark labels (only modified when adding new scripts)
- `data/` (all intermediate files and results logs)
- `program.md` — This file

---

## Editable Files

During research, you may ONLY modify these files:

### 1. `config/rubric_prompt.md`
The evaluation rubric and scoring guidelines.

**What you can change:**
- Wording of dimension definitions
- Scoring scale descriptions (e.g., what makes a "7" vs an "8")
- Examples or clarifications
- Guidelines for consistency

**What you cannot change:**
- Add/remove evaluation dimensions (only modify the 8 defined dimensions)
- Change the evaluation scale (stays 1-10)
- Fundamentally change how scores are interpreted

**Example modifications:**
- Clarify what "commercial viability" means
- Add specific genre-based scoring guidance
- Refine the ranking categories (Pass, Maybe, Consider, etc.)

### 2. `config/extraction_prompt.md`
Feature extraction instructions for the LLM.

**What you can change:**
- Clarify what features to extract
- Add/remove extraction fields (must be reasonable)
- Improve prompts for clarity

**What you cannot change:**
- Fundamentally alter the approach to extraction
- Change the output JSON structure in ways that break downstream processing

### 3. `config/evaluator_config.json`
Evaluation weights and configuration.

**What you can change:**
- Dimension weights (must sum to 1.0)
- Caching settings
- Model temperature and token limits

**What you cannot change:**
- The dimensions themselves (8 fixed dimensions)
- Evaluation scale (1-10)
- Aggregation strategy without code changes

**Example weight adjustments:**
```json
{
  "weights": {
    "concept_strength": 0.20,
    "character_strength": 0.15,
    "dialogue_quality": 0.15,
    "structure_pacing": 0.15,
    "originality": 0.15,
    "commercial_viability": 0.12,
    "producibility": 0.08
  }
}
```

---

## Research Workflow

### Step 1: Set Up (one-time)

```bash
# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and add your API keys
cp .env.example .env
# Edit .env and add ANTHROPIC_API_KEY and/or OPENAI_API_KEY

# Ingest PDFs from your source folder
python src/cli.py ingest-pdfs --pdf-source /path/to/your/pdfs

# Build benchmark dataset
python src/cli.py build-benchmark --labels-csv /path/to/labels.csv
```

### Step 2: Run Baseline Evaluation

```bash
# Evaluate all scripts with current configuration
python src/cli.py run-eval
```

This will:
1. Load the benchmark
2. Run evaluator on all scripts
3. Save results to `data/results/`
4. Log metrics to `data/results/results.tsv`

### Step 3: Propose Experiment

Decide what to change and why:

- "Increase weight on 'originality' because we're missing shows that are different"
- "Clarify 'dialogue quality' rubric because LLM is giving inconsistent scores"
- "Adjust producibility weights because high-budget shows are being over-favored"

### Step 4: Make Changes

Modify ONE of the editable files. Document your change:

```bash
# Example: Adjust weights
# Edit config/evaluator_config.json
# Changed originality weight from 0.15 to 0.20
```

Keep changes focused and small. Better to run 5 small experiments than 1 large one.

### Step 5: Re-evaluate

```bash
# Run evaluation again with modified config
python src/cli.py run-eval

# Compare results
python src/cli.py show-results
```

Compare new results against baseline:
- Are top-ranked scripts more sensible?
- Do winners/losers align better with labels?
- Is the distribution of scores more reasonable?

### Step 6: Keep or Discard

**Keep the change if:**
- New results better align with labeled benchmark
- Top-ranked scripts are more sensible
- Scores are more consistent across reruns
- No regressions in other dimensions

**Discard the change if:**
- Results got worse
- Scores became more erratic
- You introduced overfitting (only works on specific scripts)

The system automatically backs up your config before changes, so you can revert.

### Step 7: Log Results

The system automatically logs experiments to `data/results/results.tsv` with:
- Timestamp and experiment ID
- Model used
- Number of scripts evaluated
- Keep/discard decision
- Notes about the change

---

## Avoiding Common Pitfalls

### 1. Overfitting
Don't modify the rubric to match specific scripts you've seen. The goal is general improvement.

**Bad:** "Increase dialogue quality weight because Script X should rank higher"
**Good:** "Increase dialogue quality weight because shows with naturally witty dialogue aren't being recognized"

### 2. Convergence
Stop making changes when metrics stabilize. Running 50 experiments doesn't guarantee better results.

**Rule:** If changes aren't improving metrics after 5 consecutive experiments, step back and reassess.

### 3. Scope Creep
Stick to small, focused changes. Don't rewrite the rubric all at once.

**Bad:** Rewrite all 8 rubric dimensions in one experiment
**Good:** Focus on 1-2 dimensions at a time

### 4. Hidden Dependencies
The extraction prompt and rubric are coupled—if you change rubric scoring, extraction might not align.

**Best practice:** When modifying rubric significantly, also review extraction prompt to ensure they're consistent.

---

## Metrics & Validation

The system computes the following metrics for labeled datasets:

- **Labeled Accuracy**: For known winners/losers, what fraction are ranked correctly?
- **Score Distribution**: Are scores distributed reasonably? (Not all 5s, not all 9s?)
- **Stability**: Do the same scripts rank consistently across reruns?
- **Ranking Correlation**: How well do our rankings match expert labels?

You can view results:

```bash
python src/cli.py show-results
```

This shows all experiments with their metrics. Use this to understand what's working.

---

## Fallback for Unlabeled Datasets

If you don't have labeled benchmark data yet, the system still works:

1. Run evaluations normally
2. Use **score distributions** and **consistency checks** to validate
3. Once you get some labeled data, add it and re-validate
4. Build labels iteratively—start with 50 scripts, expand to 200, etc.

---

## Command Reference

```bash
# Ingest PDFs
python src/cli.py ingest-pdfs [--pdf-source PATH] [--skip-existing]

# Build benchmark
python src/cli.py build-benchmark [--pdf-source PATH] [--labels-csv PATH]

# Run evaluation
python src/cli.py run-eval [--model claude|openai] [--script-ids ID1,ID2,...]

# Show results
python src/cli.py show-results
```

---

## File Structure

```
autoresearch/
├── config/
│   ├── config.json          ← Main config (DON'T EDIT)
│   ├── evaluator_config.json ← EDITABLE: weights, aggregation
│   ├── rubric_prompt.md      ← EDITABLE: scoring rubric
│   └── extraction_prompt.md  ← EDITABLE: feature extraction
├── src/
│   ├── cli.py               ← IMMUTABLE
│   ├── config.py
│   ├── ingestion.py
│   ├── benchmark.py
│   ├── evaluator.py
│   ├── metrics.py
│   └── research_loop.py
├── data/
│   ├── pdfs/               ← Your screenplay PDFs
│   ├── extracted_text/     ← Auto-generated text files
│   ├── benchmark/          ← Benchmark labels & metadata
│   └── results/            ← Experiment logs & metrics
├── requirements.txt
├── .env
├── .env.example
└── program.md              ← This file
```

---

## Debugging

If evaluation fails:

1. Check API keys in `.env`
2. Ensure PDFs are in the right folder
3. Run small evaluation first: `python src/cli.py run-eval --script-ids script_1,script_2`
4. Check `data/results/` for error logs

---

## Questions?

Refer to:
- `config/rubric_prompt.md` — What are we evaluating?
- `config/evaluator_config.json` — How are scores weighted?
- `data/results/results.tsv` — What experiments have we run?
