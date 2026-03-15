# GEM Research Pipeline — TV Script Factor Analysis

Research infrastructure for identifying which factors in TV pilot scripts best predict breakout success.

## Dataset

- **1,102 shows** from the Master Pilots List (73 winners, 1,029 losers)
- **909 pilot scripts** as PDFs in `data/scripts/pdf_backup/`
- **809 shows** successfully linked to scripts (52 winners, 757 losers)

## Quick Start

```bash
cd research

# 1. Ingest — parse sheet + link scripts
python cli.py ingest

# 2. Inspect labels — see how schemes partition the data
python cli.py labels

# 3. List candidate factors
python cli.py factors

# 4. Analyze scripts (--mock for testing, remove for real Claude API analysis)
python cli.py analyze --mock
# For real analysis: ANTHROPIC_API_KEY=... python cli.py analyze

# 5. Hypothesis testing — compare factors across label schemes
python cli.py test

# 6. Generate full report
python cli.py report
```

## Pipeline Stages

### Phase 1 — Ingest (`ingest.py`)
- Parses `Master Pilots list - 2.0.pdf` → structured CSV in `data/sheets/`
- Loads script PDFs via PyPDF2
- Links sheet rows to scripts by PDF filename (primary) and fuzzy title matching (fallback)
- Outputs `data/linked_dataset.json`

### Phase 2 — Labeling (`labels.py`)
Three built-in label schemes to test factor stability:
- **binary_all** — All 52 winners vs 757 losers
- **strict_confident** — Only high-confidence filename matches
- **balanced_sample** — 52 winners vs 52 randomly sampled losers (controls for class imbalance)

### Phase 3 — Factors (`factors.py`)
12 candidate factors scored 1-10:
- premise_strength, hook_clarity, character_magnetism, series_engine
- originality, emotional_pull, world_distinctiveness, scene_propulsion
- dialogue_sharpness, commercial_clarity, derivative_risk, word_of_mouth_potential

### Phase 4 — Analysis (`analyze.py`)
- Sends each script to Claude for structured factor scoring
- Caches results in `output/analyses/`
- Mock mode available for testing without API

### Phase 5 — Hypothesis Testing (`hypothesis.py`)
- Cohen's d effect size for each factor across winner/loser groups
- Welch's t-test for significance
- Stability analysis across all three label schemes
- False positive/negative detection

### Phase 6 — Reporting (`report.py`)
- `output/report.json` — structured data
- `output/report.txt` — human-readable summary
- Ranked factors, stable/unstable classification, recommendations

## Dependencies

```bash
pip install pydantic PyPDF2
# For real analysis (not mock):
pip install anthropic
```

## File Structure

```
research/
├── cli.py              # CLI entry point (7 commands)
├── models.py           # Pydantic data models
├── ingest.py           # Sheet + script loading + linking
├── labels.py           # Flexible labeling schemes
├── factors.py          # 12 candidate factor definitions
├── analyze.py          # Claude API script analysis
├── hypothesis.py       # Statistical testing
├── report.py           # Report generation
├── data/
│   ├── sheets/         # Master Pilots List CSV
│   └── scripts/        # pdf_backup/ with 909 pilot PDFs
└── output/
    ├── analyses/       # Per-show analysis JSON files
    ├── report.json     # Structured report
    └── report.txt      # Human-readable report
```
