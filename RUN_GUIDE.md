# GEM Research Pipeline — Local Run Guide

## Setup (one time)

```bash
cd autoresearch/
pip install -r requirements.txt

# Set your API key
export OPENAI_API_KEY=your_key_here
# or: cp .env.example .env && edit .env
```

---

## Current System State

| Component | Status |
|-----------|--------|
| Corpus | 1,107 shows registered, 909 with pilot scripts |
| Scoring v2 (baseline) | Complete — 906 scripts, 84.01% holdout accuracy |
| Labels v2 | Active — 72 winners, 8 middle, 1,027 losers (50 flagged for review) |
| Scoring v3 (expanded) | Pending — ready to run after dimensions are added |

---

## The Next Run: v3 Expanded

### Step 1 — Add your new dimensions

Edit `config/new_dimensions.json`. Each dimension looks like:

```json
[
  {
    "name": "resonant_originality",
    "display_name": "Resonant Originality",
    "what_it_measures": "Does the show feel new AND inevitable — risky but immediately landing?",
    "strong_signals": [
      "Bold formal/structural choices that feel earned, not alienating",
      "Premise is fresh but instantly legible — you haven't seen it but you get it"
    ],
    "weak_signals": [
      "Bold in ways that confuse or alienate — risky but not landing",
      "Derivative but well-executed — safe originality"
    ],
    "anchors": {
      "9-10": "Breaking Bad: antihero premise was totally novel yet felt inevitable",
      "7-8": "The Americans: fresh angle on spy genre but took a season to fully land",
      "5-6": "A competent procedural with one unusual twist",
      "3-4": "Derivative premise with ineffective attempts at freshness",
      "1-2": "Pure imitation with no distinguishing voice"
    }
  }
]
```

### Step 2 — Preview the run (no cost)

```bash
python3 src/score_run.py --run v3_expanded --dry-run
```

Shows: how many scripts to score, estimated cost, prompt preview.

### Step 3 — Test on 10 scripts

```bash
python3 src/score_run.py --run v3_expanded --limit 10
```

Cost: ~$0.10. Verify output looks right before full run.

### Step 4 — Full run

```bash
python3 src/score_run.py --run v3_expanded
```

Cost: ~$9 for 909 scripts. Resumes automatically if interrupted. Takes ~45 min.

### Step 5 — Re-run analysis only (free, after scoring is done)

```bash
python3 src/score_run.py --run v3_expanded --analyze-only
```

Runs gap analysis + weight optimizer. Shows which new dimensions add signal.

---

## Corpus Expansion

### Add a new show (manual script)

```bash
# Register the show
python3 src/corpus_manager.py add "my_show_101_pilot" "My Show" --label winner

# Copy in the script
python3 src/corpus_manager.py add-script "my_show_101_pilot" /path/to/script.txt
```

### Add a show with web-gathered evidence (no script)

```bash
# Register
python3 src/corpus_manager.py add "beef_101_pilot" "Beef" --label winner

# Gather summary/logline/metadata via LLM
python3 src/corpus_manager.py gather "beef_101_pilot"
```

### Batch-gather evidence for many shows

Create a text file with one show_id per line, then:

```bash
python3 src/corpus_manager.py gather-batch my_show_list.txt
```

### Check corpus status

```bash
python3 src/corpus_manager.py status
python3 src/corpus_manager.py ready-to-score
```

---

## Label Management

```bash
# See current stats
python3 src/label_manager.py stats

# See all flagged items (non-interactive)
python3 src/label_manager.py review-list

# Interactive review (prompted)
python3 src/label_manager.py review

# Manually reclassify a show
python3 src/label_manager.py set "Sherlock_1x01_-_A_Study_In_Scarlet" middle

# Export labels for pipeline use
python3 src/label_manager.py export
```

---

## Scoring Versions

```bash
# See all scoring versions and their status
python3 src/score_run.py list-runs
```

| Version | Location | Notes |
|---------|----------|-------|
| v2_baseline | data/scoring/v2_baseline/ + data/results/live/per_script/ | READ ONLY. Never touch. |
| v3_expanded | data/scoring/v3_expanded/per_script/ | New run — add dimensions, then run |

---

## After v3 Run Completes

1. **Check gap analysis** — which new dimensions show the highest winner/loser gap?
2. **Check optimized weights** — which new dimensions does the optimizer keep vs zero out?
3. **Compare holdout accuracy** — did we beat 84.01%?
4. **Run autoresearch loop** — if new dimensions help, add more in batches

The optimizer is the ground truth. High raw gap + non-zero weight = genuine signal.

---

## File Structure Reference

```
autoresearch/
├── config/
│   ├── new_dimensions.json       ← ADD YOUR NEW DIMENSIONS HERE
│   ├── rubric_v2_producer_mind.md
│   └── scoring_runs/
│       └── v3_expanded.json      ← Run config
├── data/
│   ├── corpus/
│   │   ├── registry.jsonl        ← All shows (old + new)
│   │   └── evidence/{show_id}/   ← Per-show evidence files
│   ├── extracted_text/           ← Existing 909 pilot scripts (DO NOT DELETE)
│   ├── labels/
│   │   ├── labels_v1.jsonl       ← Original binary labels (READ ONLY)
│   │   ├── labels_v2.jsonl       ← Active 3-bucket labels
│   │   └── LABELING_GUIDE.md
│   ├── results/                  ← v2 baseline outputs (DO NOT TOUCH)
│   │   └── live/per_script/      ← 909 v2 scored JSONs
│   └── scoring/
│       ├── v2_baseline/manifest.json   ← Describes v2 run
│       └── v3_expanded/
│           ├── manifest.json           ← Run metadata
│           └── per_script/             ← v3 scored JSONs (populated by score_run.py)
└── src/
    ├── score_run.py              ← Main scoring runner
    ├── label_manager.py          ← Label CRUD + review
    ├── corpus_manager.py         ← Corpus expansion
    └── add_dimensions.py         ← Legacy (still works for append-only patches)
```
