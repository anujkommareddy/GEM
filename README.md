# GEM Autoresearch: Iterative Screenplay Evaluator

A local, research-oriented system for iteratively improving screenplay evaluation using LLM-based scoring.

Inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch), adapted for evaluating TV pilots and screenplays.

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up API Keys

```bash
cp .env.example .env
# Edit .env and add your API keys:
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
```

### 3. Place Your PDFs

Copy your screenplay PDFs to `data/pdfs/`:

```bash
mkdir -p data/pdfs
# Copy your .pdf files into data/pdfs/
```

### 4. Ingest PDFs

Extract text from PDFs:

```bash
python src/cli.py ingest-pdfs
```

Output:
- `data/extracted_text/*.txt` — Extracted screenplay text
- `data/extracted_text/metadata.jsonl` — PDF metadata and extracted text paths

### 5. Build Benchmark

Create the benchmark dataset:

```bash
# Without labels (initial setup)
python src/cli.py build-benchmark

# With labels (if you have them)
python src/cli.py build-benchmark --labels-csv labels.csv
```

Expected CSV format:
```
script_id,show_name,label,outcome,human_score,notes
10_Things_I_Hate_About_You_1x01_-_Pilot,10 Things I Hate About You,winner,1,8.0,
12_Monkeys_1x01_-_Pilot,12 Monkeys,winner,1,8.5,
```

Output:
- `data/benchmark/benchmark.jsonl` — Benchmark with script IDs, paths, and labels

### 6. Run Evaluation

Evaluate all scripts:

```bash
python src/cli.py run-eval
```

Or specific scripts:

```bash
python src/cli.py run-eval --script-ids script_1,script_2
python src/cli.py run-eval --model claude
python src/cli.py run-eval --model openai
```

Output:
- `data/results/eval_results_*.jsonl` — Detailed evaluation results
- `data/results/results.tsv` — Experiment log with metrics

### 7. View Results

```bash
python src/cli.py show-results
```

## Research Workflow

Once set up, the typical research loop is:

1. **Run baseline evaluation** → `python src/cli.py run-eval`
2. **Propose change** → Document what you're changing and why
3. **Modify config file** → Edit one of the editable files (see below)
4. **Re-evaluate** → `python src/cli.py run-eval`
5. **Compare results** → `python src/cli.py show-results`
6. **Keep or discard** → Accept if metrics improve, revert if they don't

**See `program.md` for detailed guidance on the research workflow.**

## Editable Files

You can modify these files during research:

- **`config/rubric_prompt.md`** — Evaluation rubric and scoring guidelines
- **`config/extraction_prompt.md`** — Feature extraction instructions
- **`config/evaluator_config.json`** — Dimension weights and aggregation settings

**See `program.md` for detailed rules on what can be modified.**

## Architecture

### Core Components

- **Ingestion** (`src/ingestion.py`) — PDF text extraction and metadata
- **Benchmark** (`src/benchmark.py`) — Dataset management and labels
- **Evaluator** (`src/evaluator.py`) — LLM-based screenplay scoring
- **Research Loop** (`src/research_loop.py`) — Experiment orchestration and config backup/restore
- **Metrics** (`src/metrics.py`) — Performance tracking and validation
- **CLI** (`src/cli.py`) — Command-line interface

### Data Flow

```
PDFs → Ingestion → Extracted Text
                        ↓
                    Benchmark + Labels
                        ↓
                    Evaluator (LLM)
                        ↓
                    Scores & Metrics
                        ↓
                    Results Log
```

## Evaluation Dimensions

The evaluator scores screenplays on 8 dimensions (1-10 scale):

1. **Concept & Premise Strength** — Is the hook clear and compelling?
2. **Character Strength** — Are characters well-drawn and distinct?
3. **Dialogue Quality** — Is dialogue natural and character-specific?
4. **Structure & Pacing** — Does it follow a clear narrative arc?
5. **Originality** — How fresh is the concept?
6. **Commercial Viability** — Does it have market potential?
7. **Producibility** — How feasible is it to produce?
8. **Overall Recommendation** — Final recommendation (Pass, Maybe, Consider, Recommend, Must Greenlight)

See `config/rubric_prompt.md` for detailed scoring rubrics.

## Models Supported

### Claude (Anthropic)

```bash
python src/cli.py run-eval --model claude
```

- Requires: `ANTHROPIC_API_KEY` in `.env`
- Default: `claude-opus-4-6`
- Configurable in `config/config.json` → `models.claude`

### OpenAI

```bash
python src/cli.py run-eval --model openai
```

- Requires: `OPENAI_API_KEY` in `.env`
- Default: `gpt-4`
- Configurable in `config/config.json` → `models.openai`

## File Structure

```
autoresearch/
├── config/
│   ├── config.json              ← Main configuration
│   ├── evaluator_config.json    ← Weights & aggregation
│   ├── rubric_prompt.md         ← EDITABLE: Evaluation rubric
│   └── extraction_prompt.md     ← EDITABLE: Feature extraction
├── src/
│   ├── cli.py                   ← Command-line interface
│   ├── config.py                ← Configuration loader
│   ├── ingestion.py             ← PDF ingestion pipeline
│   ├── benchmark.py             ← Benchmark dataset management
│   ├── evaluator.py             ← Screenplay evaluator
│   ├── metrics.py               ← Metrics & logging
│   └── research_loop.py         ← Research loop orchestration
├── data/
│   ├── pdfs/                    ← Your screenplay PDFs (input)
│   ├── extracted_text/          ← Extracted text (auto-generated)
│   ├── benchmark/               ← Benchmark dataset & labels
│   └── results/                 ← Experiment logs & metrics
├── requirements.txt
├── .env                         ← Your API keys (GITIGNORED)
├── .env.example                 ← Template for .env
├── program.md                   ← Research operating manual
└── README.md                    ← This file
```

## Results & Metrics

Results are logged to `data/results/results.tsv` with columns:

- **timestamp** — When the experiment ran
- **experiment_id** — Unique experiment ID
- **model** — Model used (claude/openai)
- **scripts_evaluated** — Number of successful evaluations
- **metrics_json** — JSON metrics (ranking accuracy, etc.)
- **files_changed** — Which config files were modified
- **keep_discard** — Whether changes were kept or discarded
- **notes** — Human notes about the experiment

View results:

```bash
python src/cli.py show-results
```

## Benchmarking Against Labels

If you have labeled data (winners/losers), the system automatically computes:

- **Ranking Accuracy** — What fraction of winner/loser pairs are ranked correctly?
- **Score Stability** — Do the same scripts rank consistently across reruns?
- **Label Correlation** — How well do our rankings align with expert labels?

This helps validate whether changes actually improve evaluation quality.

## Limitations & Future Work

- Currently supports Claude and OpenAI. Easy to add other LLM providers.
- PDF extraction uses `pdfplumber` with basic OCR. Complex layouts may need improvement.
- Evaluation is resource-intensive (one LLM call per script per dimension).
- No built-in A/B testing framework yet.

## References

- [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) — Inspiration
- [pdfplumber](https://github.com/jsvine/pdfplumber) — PDF text extraction
- [Anthropic Claude API](https://docs.anthropic.com/) — LLM provider
- [OpenAI API](https://platform.openai.com/docs/) — Alternative LLM provider

## License

Local research project for GEM Media Lab.

## Next Steps

1. **Set up**: Follow Quick Start above
2. **Read**: Review `program.md` for research guidelines
3. **Establish baseline**: Run initial evaluations with default config
4. **Iterate**: Make small, focused changes and measure impact
5. **Improve**: Keep changes that help, discard those that don't

Good luck!
