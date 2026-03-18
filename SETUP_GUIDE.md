# GEM Autoresearch Setup Guide

Complete step-by-step instructions to set up and run the autoresearch system locally.

## Prerequisites

- Python 3.8+
- Your screenplay PDFs in a local folder
- (Optional) Labels CSV file with winners/losers
- API keys for Claude (Anthropic) and/or OpenAI

## Step 1: Install Dependencies

```bash
cd ~/documents/selznick_3/autoresearch

# Install Python dependencies
pip install -r requirements.txt
```

Expected packages:
- `pdfplumber` — PDF text extraction
- `anthropic` — Claude API client
- `openai` — OpenAI API client
- `python-dotenv` — Environment variable management

## Step 2: Set Up API Keys

```bash
# Copy the example env file
cp .env.example .env

# Edit .env and add your API keys
# For Claude: ANTHROPIC_API_KEY=sk-ant-...
# For OpenAI: OPENAI_API_KEY=sk-...
```

You need at least one API key to run evaluations:

**Claude (Recommended for this project):**
- Get key from: https://console.anthropic.com/account/keys
- Add to `.env`: `ANTHROPIC_API_KEY=your_key`

**OpenAI (Alternative):**
- Get key from: https://platform.openai.com/account/api-keys
- Add to `.env`: `OPENAI_API_KEY=your_key`

## Step 3: Prepare Your PDFs

Ensure your screenplay PDFs are in one folder:

```bash
# If PDFs are in ~/documents/selznick_3/pdf_backup/ (as they currently are):
mkdir -p data/pdfs
cp /Users/[YOUR_USERNAME]/Documents/Selznick_3/pdf_backup/*.pdf data/pdfs/

# OR point the system to your PDF folder via config
# (See config/config.json → paths.pdf_source)
```

## Step 4: Run Ingestion Pipeline

Extract text from PDFs:

```bash
python main.py ingest-pdfs
```

What this does:
1. Scans `data/pdfs/` for all `.pdf` files
2. Extracts text from each PDF using pdfplumber
3. Saves extracted text to `data/extracted_text/*.txt`
4. Creates `data/extracted_text/metadata.jsonl` with file metadata

Expected output:
```
✓ Ingested 900+ scripts
  Extracted text saved to: ./data/extracted_text
  Metadata saved to: ./data/extracted_text/metadata.jsonl
```

## Step 5: Build Benchmark Dataset

Create the benchmark:

```bash
# WITHOUT labels (initial setup)
python main.py build-benchmark

# WITH labels (if you have winners/losers data)
python main.py build-benchmark --labels-csv labels.csv
```

**If you have labels:**

Prepare a CSV file with columns:
```
script_id,show_name,label,outcome,human_score,notes
10_Things_I_Hate_About_You_1x01_-_Pilot,10 Things I Hate About You,winner,1,8.0,Successful show
12_Monkeys_1x01_-_Pilot,12 Monkeys,loser,0,3.0,Cancelled after one season
```

What this does:
1. Loads ingested PDF metadata
2. (Optional) Adds human labels from CSV
3. Creates `data/benchmark/benchmark.jsonl` with script info and labels
4. Prepares data for evaluation

## Step 6: Run Baseline Evaluation

Evaluate all scripts with the default configuration:

```bash
# Using Claude (recommended, default)
python main.py run-eval

# OR using OpenAI
python main.py run-eval --model openai

# OR specific scripts only (faster for testing)
python main.py run-eval --script-ids script_1,script_2,script_3
```

This will:
1. Load the benchmark
2. For each script:
   - Extract key features using Claude/OpenAI
   - Score on 8 dimensions
   - Aggregate scores
3. Save results to `data/results/eval_results_TIMESTAMP.jsonl`
4. Log metrics to `data/results/results.tsv`

Expected runtime:
- 5 scripts: ~2-3 minutes
- 100 scripts: ~30-40 minutes
- 900+ scripts: ~4-6 hours (depending on API rate limits)

## Step 7: View Results

```bash
python main.py show-results
```

This displays a table of all experiments with:
- Timestamp
- Experiment ID
- Model used
- Number of scripts evaluated
- Keep/discard status
- Notes

## Step 8: Start Research Loop

Now you can iteratively improve the evaluator:

1. **Make a hypothesis** — "If I clarify the dialogue quality rubric, scores will better match expert labels"

2. **Modify a config file** (ONE of these):
   - `config/rubric_prompt.md` — Change evaluation guidelines
   - `config/extraction_prompt.md` — Change feature extraction
   - `config/evaluator_config.json` — Change dimension weights

   Example: Edit `config/evaluator_config.json` to change weights:
   ```json
   "weights": {
     "concept_strength": 0.20,  // Increased from 0.15
     "character_strength": 0.15,
     ...
   }
   ```

3. **Re-evaluate** — `python main.py run-eval`

4. **Compare results** — `python main.py show-results`

5. **Keep or discard** — If metrics improve, keep it. Otherwise, config is automatically restored from backup.

## File Structure After Setup

```
autoresearch/
├── config/                          ← Edit these during research
│   ├── evaluator_config.json        ← Dimension weights
│   ├── rubric_prompt.md             ← Evaluation rubric
│   └── extraction_prompt.md         ← Feature extraction
│
├── data/
│   ├── pdfs/                        ← Your screenplay PDFs (input)
│   ├── extracted_text/              ← Auto-generated text files
│   │   ├── script_1.txt
│   │   ├── script_2.txt
│   │   └── metadata.jsonl           ← Metadata for all scripts
│   │
│   ├── benchmark/
│   │   └── benchmark.jsonl          ← Benchmark with labels
│   │
│   └── results/
│       ├── eval_results_*.jsonl     ← Detailed evaluation results
│       └── results.tsv              ← Experiment log
│
├── src/                             ← DO NOT EDIT
│   ├── cli.py
│   ├── config.py
│   ├── ingestion.py
│   ├── benchmark.py
│   ├── evaluator.py
│   ├── metrics.py
│   └── research_loop.py
│
├── main.py                          ← Entry point
├── program.md                       ← Research operating manual
└── README.md                        ← Project documentation
```

## Troubleshooting

### "No PDF files found"
- Check that PDFs are in `data/pdfs/`
- Ensure file extensions are `.pdf` (lowercase)
- Run `ls data/pdfs/*.pdf` to verify

### "Could not load text for script_id"
- Run ingestion again: `python main.py ingest-pdfs`
- Check that extracted text exists: `ls data/extracted_text/*.txt`

### API Key errors
- Ensure `.env` file exists in the autoresearch directory
- Check that API key is correct in `.env`
- For Claude: https://console.anthropic.com/account/keys
- For OpenAI: https://platform.openai.com/account/api-keys

### PDF extraction issues (empty text)
- Some PDFs might be scanned images (not text-based)
- `pdfplumber` works best on text-based PDFs
- OCR support can be added if needed

### Out of memory or rate limits
- Run smaller batches: `python main.py run-eval --script-ids script_1,script_2`
- Add delays between API calls in `src/evaluator.py` if hitting rate limits
- Check API quota at https://platform.openai.com/ or Anthropic console

## Next Steps

1. Complete Setup steps 1-6 above
2. Read `program.md` for research guidelines
3. Start your first experiment by modifying a config file
4. Iterate and improve!

## Manual Label File for Master Pilots List

If you want to use the "Master Pilots list - 2.0.pdf" file with winners/losers:

1. I tried to extract it but the PDF structure is complex
2. **Option A:** Share the file in a different format (CSV, Excel, JSON)
3. **Option B:** I can help extract it more carefully if you share the file contents

For now, the system works without labels—you can add them later once they're in a CSV or JSON format.

## Questions or Issues?

Refer to:
- `README.md` — Project overview and architecture
- `program.md` — Research workflow and guidelines
- `config/rubric_prompt.md` — What each dimension means
- `data/results/results.tsv` — History of experiments
