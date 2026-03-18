# GEM Research Pipeline — TV Script Factor Analysis

Research infrastructure for identifying which factors in TV pilot scripts best predict breakout success.

## Dataset

- **1,102 shows** from the Master Pilots List (73 winners, 1,029 losers)
- **909 pilot scripts** as PDFs in `data/scripts/`
- **809 shows** successfully linked to scripts (52 winners, 757 losers)

## Quick Start

```bash
cd research

# 1. Ingest — parse sheet + link scripts
python cli.py ingest

# 2. Inspect labels — see how schemes partition the data
python cli.py labels

# 3. List the 5 core facets
python cli.py facets

# 4. Analyze scripts (--mock for testing without API calls)
python cli.py analyze --mock

# For real analysis with OpenAI (default):
python cli.py analyze

# For real analysis with Anthropic:
python cli.py analyze --provider anthropic

# Specify a model explicitly:
python cli.py analyze --provider openai --model gpt-4o

# 5. Hypothesis testing — compare facets across label schemes
python cli.py test

# 6. Generate full report
python cli.py report

# Check pipeline status at any time
python cli.py status
```

## Pipeline Stages

### Phase 1 — Ingest (`ingest.py`)
- Parses Master Pilots List CSV → structured records
- Loads script files (PDF, TXT, FDX, Fountain)
- Links sheet rows to scripts by filename and fuzzy title matching
- Outputs `data/linked_dataset.json`

### Phase 2 — Labeling (`labels.py`)
Three built-in label schemes to test facet stability:
- **binary_all** — All 52 winners vs 757 losers
- **strict_confident** — Only high-confidence filename matches
- **balanced_sample** — 52 winners vs 52 randomly sampled losers

### Phase 3 — Facets (`factors.py`)
5 core facets scored 1-10:
- `audience_appeal_marketability` — Commercial reach & broad audience interest
- `conceptual_hook_clarity` — How instantly graspable the premise is
- `character_appeal_and_long_term_potential` — Charisma, memorability, multi-season arcs
- `creative_originality_and_boldness` — Freshness of voice/structure, risk-taking
- `narrative_momentum_engagement` — Pacing, escalation, compulsion to continue

### Phase 4 — Analysis (`analyze.py`)
- Sends each script to an AI model for structured facet scoring
- Supports OpenAI (default) and Anthropic providers
- Caches results in `output/analyses/`
- Mock mode available for testing without API calls

### Phase 5 — Hypothesis Testing (`hypothesis.py`)
- Cohen's d effect size for each facet across winner/loser groups
- Welch's t-test for significance
- Stability analysis across all three label schemes

### Phase 6 — Reporting (`report.py`)
- `output/report.json` — structured data
- `output/report.txt` — human-readable summary
- Ranked facets, stable/unstable classification, recommendations

## Providers & Models

| Provider | Default Model | Env Var |
|----------|--------------|---------|
| OpenAI | gpt-4o-mini | `OPENAI_API_KEY` |
| Anthropic | claude-haiku-4-5 | `ANTHROPIC_API_KEY` |

Supported models: `gpt-4o-mini`, `gpt-4o`, `gpt-4.1-nano`, `claude-haiku-4-5-20251001`, `claude-sonnet-4-20250514`

## File Structure

```
research/
├── cli.py              # CLI entry point (7 commands)
├── models.py           # Pydantic data models
├── ingest.py           # Sheet + script loading + linking
├── labels.py           # Flexible labeling schemes
├── factors.py          # 5 core facet definitions
├── analyze.py          # AI-powered script analysis
├── hypothesis.py       # Statistical testing
├── report.py           # Report generation
├── providers.py        # OpenAI + Anthropic provider abstraction
├── requirements.txt    # Python dependencies
├── data/
│   ├── sheets/         # Master Pilots List CSV
│   ├── scripts/        # Pilot script PDFs + TXT files
│   └── linked_dataset.json
└── output/
    ├── analyses/       # Per-show analysis JSON files
    ├── report.json
    └── report.txt
```
