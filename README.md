# GEM — Generative Entertainment Machine

Two pipelines in one repo:

1. **Research Pipeline** (`research/`) — Analyze TV pilot scripts to identify what predicts breakout success using AI-powered facet scoring and statistical testing.
2. **Video Pipeline** (`src/`) — Concept-to-clips pipeline for AI-generated films (Anthropic + Higgsfield).

---

## Research Pipeline (the main thing right now)

### What it does

Takes ~900 TV pilot scripts, sends them through an AI model (OpenAI or Anthropic) for structured scoring on 5 facets (audience appeal, conceptual hook, character appeal, creative originality, narrative momentum), then runs statistical tests to see which facets actually distinguish winners from losers across multiple labeling schemes.

### Install

```bash
cd research
pip install -r requirements.txt
```

### Configure

Copy the env template and add your API key:

```bash
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=sk-...
```

The `.env` file goes in the **repo root** (`GEM/.env`). The CLI loads it automatically.

### Input data

Place your data in:
- `research/data/sheets/master_pilots_list.csv` — the master show list
- `research/data/scripts/` — pilot script PDFs and/or TXT files

The `linked_dataset.json` in `research/data/` is the pre-linked dataset (already committed).

### Run the pipeline

```bash
cd research

# Check what's ready
python cli.py status

# Step 1: Link shows to scripts (already done if linked_dataset.json exists)
python cli.py ingest

# Step 2: Inspect label distributions
python cli.py labels

# Step 3: Test with mock analysis (free, no API calls)
python cli.py analyze --mock

# Step 4: Run real analysis with OpenAI
python cli.py analyze

# Or with Anthropic:
python cli.py analyze --provider anthropic

# Or with a specific model:
python cli.py analyze --provider openai --model gpt-4o

# Step 5: Run hypothesis testing
python cli.py test

# Step 6: Generate report
python cli.py report
```

### Output

Results go to `research/output/`:
- `analyses/` — One JSON file per show with facet scores
- `report.json` — Structured report
- `report.txt` — Human-readable summary

### Provider/model selection

| Flag | Example | Default |
|------|---------|---------|
| `--provider` | `openai`, `anthropic` | `openai` |
| `--model` | `gpt-4o-mini`, `gpt-4o`, `gpt-4.1-nano` | `gpt-4o-mini` |

Environment variables: `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (set in `.env`).

---

## Video Pipeline

```bash
bun run gem              # Start the video pipeline
```

Requires `ANTHROPIC_API_KEY` and `HF_CREDENTIALS` in `.env`.

See `CLAUDE.md` for stage details.
