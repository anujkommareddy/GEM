# GEM Research Pipeline

Script factor analysis pipeline for studying what distinguishes TV show winners from losers.

## Setup

```bash
pip install pydantic
pip install anthropic   # only needed for real (non-mock) analysis
```

## Data Preparation

1. **Export your Google Sheet** as CSV and place it in `data/sheets/`
2. **Copy your script files** into `data/scripts/`
   - Supports: `.txt`, `.pdf`, `.fdx` (Final Draft), `.fountain`, `.md`
   - Naming conventions (any of these work):
     - `Show Name - Pilot.txt`
     - `Show Name - S01E01 - Episode Title.txt`
     - `show_name.txt`
     - Or organize as `data/scripts/ShowName/episode.txt`

## Usage

All commands run from the `research/` directory:

```bash
# 1. Check pipeline status
python cli.py status

# 2. Ingest and link your data
python cli.py ingest data/sheets/my_shows.csv data/scripts/

# 3. Inspect label schemes
python cli.py labels

# 4. View candidate factors
python cli.py factors

# 5. Run analysis (--mock for testing without API)
python cli.py analyze --mock
# Or with real Claude analysis:
ANTHROPIC_API_KEY=sk-... python cli.py analyze

# 6. Run hypothesis testing
python cli.py test

# 7. Generate full report
python cli.py report
```

## Pipeline Phases

| Phase | Module | Purpose |
|-------|--------|---------|
| 1 | `ingest.py` | Load sheet + scripts, link by title, normalize |
| 2 | `labels.py` | Flexible winner/loser definitions, multiple schemes |
| 3 | `factors.py` | 12 candidate factors with definitions and rationale |
| 4 | `analyze.py` | Script analysis via Claude API, structured JSON output |
| 5 | `hypothesis.py` | Factor comparison, stability testing across schemes |
| 6 | `report.py` | Summary reports (JSON + text) with recommendations |

## Label Schemes

The pipeline tests your data under multiple winner/loser interpretations:

- **binary_strict** — Only clear winners and losers, excludes ambiguous
- **binary_broad** — Includes moderate cases, ambiguous kept separate
- **top_vs_bottom** — Only breakout hits vs total flops, everything else excluded

You can add custom schemes in `labels.py` or programmatically via `create_scheme_from_raw_values()`.

## Factors Analyzed

| Factor | What It Measures |
|--------|-----------------|
| premise_strength | Is the central idea compelling and pitchable? |
| hook_clarity | Does the opening grab attention and set stakes? |
| character_magnetism | Are the characters watchable and distinctive? |
| series_engine | Can this generate new stories for 100+ episodes? |
| originality | Does it feel fresh vs. what's already on air? |
| emotional_pull | Does it generate genuine emotional response? |
| world_distinctiveness | Is the world vivid and immersive? |
| scene_propulsion | Does every scene create momentum? |
| dialogue_sharpness | Is the dialogue distinctive and quotable? |
| commercial_clarity | How easy is this to market? |
| derivative_risk | How much does this feel like a copy? (risk factor) |
| word_of_mouth_potential | Will viewers actively recommend this? |

## Output

- `output/analyses/` — Per-show JSON analysis files (cached)
- `output/report.json` — Structured report data
- `output/report.txt` — Human-readable summary with recommendations

## Directory Structure

```
research/
├── cli.py              # CLI entry point
├── models.py           # Pydantic data models
├── ingest.py           # Phase 1: data loading and linking
├── labels.py           # Phase 2: flexible labeling
├── factors.py          # Phase 3: factor definitions
├── analyze.py          # Phase 4: script analysis
├── hypothesis.py       # Phase 5: hypothesis testing
├── report.py           # Phase 6: reporting
├── data/
│   ├── sheets/         # Place CSV exports here
│   └── scripts/        # Place script files here
└── output/
    ├── analyses/       # Cached analysis results
    ├── report.json     # Structured report
    └── report.txt      # Text report
```
