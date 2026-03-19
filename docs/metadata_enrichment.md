# GEM Metadata Enrichment Pipeline

## What This Does

`src/enrich_metadata.py` enriches each show in the GEM corpus with publicly available
show-level information sourced from Wikipedia. It stores structured metadata per-show
as a typed evidence layer (`evidence_type = "show_metadata"`) that is completely
additive — it never modifies or overwrites existing pilot script evidence.

The pipeline covers all 1,107 shows in the current corpus.

---

## Where Data Is Stored

```
data/metadata/
  {show_id}.json          ← one file per show (structured metadata)
  _manifest.jsonl         ← log of every enrichment attempt
  _coverage_report.json   ← field-level coverage stats across full corpus
```

Each metadata file is keyed by the same `show_id` used throughout the corpus,
ensuring stable linkage to pilot scripts, labels, and scoring outputs.

**Example:** `data/metadata/Breaking_Bad_1x01_-_Pilot.json`

---

## Data Schema

Each `{show_id}.json` contains the following fields:

### Evidence Envelope
| Field | Description |
|-------|-------------|
| `show_id` | Corpus identifier (matches registry.jsonl) |
| `evidence_type` | Always `"show_metadata"` |
| `source_type` | Always `"wikipedia"` |
| `source_url` | Direct Wikipedia URL |
| `wiki_page_title` | Exact Wikipedia page title used |
| `retrieval_timestamp` | ISO 8601 UTC timestamp |
| `retrieval_confidence` | `high / medium / low / very_low / none` |

### Basic Identity
| Field | Description |
|-------|-------------|
| `title` | Canonical show title |
| `search_title_used` | Clean title used for Wikipedia search |
| `alternate_titles` | Alternative titles (if found) |
| `start_year` | First air year |
| `end_year` | Final air year (null if ongoing) |
| `country` | Country of origin |
| `original_language` | Language(s) |

### Format / Structure
| Field | Description |
|-------|-------------|
| `genres` | List of genres |
| `format_type` | `drama / comedy / sitcom / procedural / anthology / limited_series / docuseries / animated / dramedy / sci_fi / fantasy / thriller_horror / reality` |
| `runtime_class` | `short-form / half-hour / hour / feature-length` |
| `seasons` | Number of seasons |
| `episodes` | Total episode count |

### Distribution / Industry
| Field | Description |
|-------|-------------|
| `original_network` | Network or platform (e.g. HBO, Netflix) |
| `production_companies` | Production company names |
| `distributor` | Distributor/studio if distinct |

### Creative Talent
| Field | Description |
|-------|-------------|
| `creators` | Show creator(s) |
| `showrunners` | Showrunner(s) if listed |
| `lead_cast` | Notable starring cast |
| `executive_producers` | Prominent executive producers |

### Premise / Content
| Field | Description |
|-------|-------------|
| `premise_summary` | First paragraph of Wikipedia extract (≤1,500 chars) |
| `wikipedia_extract` | Full Wikipedia lead section (≤3,000 chars) |

### Reception / Outcome
| Field | Description |
|-------|-------------|
| `cancellation_status` | `cancelled / renewed / ended_{year}` |
| `reception_notes` | Placeholder for future parsing |
| `awards_summary` | Placeholder for future parsing |
| `franchise_status` | Placeholder for future parsing |

---

## How to Run

### Full run (all 1,107 shows)
```bash
cd autoresearch
python3 src/enrich_metadata.py
```
Estimated time: ~60–90 minutes (respects Wikipedia's rate limits at ~1 req/sec).
Estimated cost: $0 (Wikipedia is free).

### Resume interrupted run
```bash
python3 src/enrich_metadata.py --resume
```
Skips shows that already have a metadata file. Safe to re-run any time.

### Dry run (preview only, no fetches)
```bash
python3 src/enrich_metadata.py --dry-run
```

### Test on first N shows
```bash
python3 src/enrich_metadata.py --limit 20
```

### Enrich a single show
```bash
python3 src/enrich_metadata.py --show "Breaking Bad"
```

### Generate coverage report only
```bash
python3 src/enrich_metadata.py --report
```

### Adjust request delay (default: 1.0 sec)
```bash
python3 src/enrich_metadata.py --delay 0.5
```

---

## How Shows Are Linked to Metadata

Each metadata file uses the same `show_id` as the corpus registry:

```python
# Load a show's metadata
import json
from pathlib import Path

show_id = "Breaking_Bad_1x01_-_Pilot"
metadata = json.loads(Path(f"data/metadata/{show_id}.json").read_text())

# Join with registry
registry = {json.loads(l)["show_id"]: json.loads(l)
            for l in open("data/corpus/registry.jsonl")}
row = registry[show_id]
```

---

## How to Add Metadata for New Shows

When new shows are added to the corpus via `src/corpus_manager.py`, run:

```bash
python3 src/enrich_metadata.py --resume
```

The `--resume` flag skips existing files and only processes new entries, so the
full corpus doesn't need to be re-fetched.

---

## Confidence Levels

The `retrieval_confidence` field indicates how well the Wikipedia page matched
the expected show title:

| Level | Meaning |
|-------|---------|
| `high` | ≥80% of title words match Wikipedia page title |
| `medium` | 50–79% word overlap |
| `low` | 25–49% word overlap |
| `very_low` | <25% word overlap — manual review recommended |
| `none` | No Wikipedia page found |

Shows with `very_low` or `none` confidence are listed in `_coverage_report.json`
under `low_confidence_shows` for manual follow-up.

---

## Coverage Report

After running, inspect the auto-generated coverage report:

```bash
cat data/metadata/_coverage_report.json | python3 -m json.tool | head -60
```

Or regenerate it at any time:

```bash
python3 src/enrich_metadata.py --report
```

---

## Architecture Notes

- **Non-destructive**: Only writes to `data/metadata/`. Never touches `data/extracted_text/`,
  `data/corpus/`, `data/scoring/`, or `data/labels/`.
- **Resume-safe**: Checks for existing file before fetching. Re-runs are idempotent.
- **Graceful failure**: If a show isn't found on Wikipedia, a stub record is saved
  with `retrieval_confidence = "none"` so the show isn't re-attempted unless
  `--resume` is omitted.
- **Rate limiting**: Default 1.0 second delay between Wikipedia requests. Adjust
  with `--delay` if you need faster/slower runs.
- **Wikipedia source**: Uses two Wikipedia APIs:
  - REST Summary API (`/api/rest_v1/page/summary/`) for description and extract
  - MediaWiki Action API (`/w/api.php`) for search and wikitext infobox parsing
