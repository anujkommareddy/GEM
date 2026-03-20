"""
gem_eval.py — GEM Single-Script Evaluator

Score a fresh, unseen TV pilot script and generate a producer report in one command.
No corpus membership required. Does not modify labels or any engine state.

Usage:
    python3 src/gem_eval.py path/to/script.pdf
    python3 src/gem_eval.py path/to/script.txt
    python3 src/gem_eval.py path/to/script.pdf --show-id "my-pilot-2026"
    python3 src/gem_eval.py path/to/script.txt --no-llm          # skip one-line synthesis
    python3 src/gem_eval.py path/to/script.pdf --out report.json  # save report to custom path

The show_id is derived from the filename if not supplied.
Scoring output is saved to:  data/scoring/v3_expanded/per_script/{show_id}.json
Report output is saved to:   data/reports/{show_id}.json
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

BASE_DIR        = Path(".")
RUNS_CONFIG_DIR = BASE_DIR / "config/scoring_runs"
V3_RUN_ID       = "v3_expanded"
PER_SCRIPT_DIR  = BASE_DIR / f"data/scoring/{V3_RUN_ID}/per_script"
WEIGHTS_FILE    = BASE_DIR / f"data/scoring/{V3_RUN_ID}/best_weights.json"
CONFIG_FILE     = BASE_DIR / "config/scoring_runs/v3_expanded.json"
RUBRIC_FILE     = BASE_DIR / "config/rubric_v2_producer_mind.md"
NEW_DIMS_FILE   = BASE_DIR / "config/new_dimensions.json"
REPORTS_DIR     = BASE_DIR / "data/reports"

MAX_CHARS = 15000   # same truncation limit as corpus scoring


# ─── Text Extraction ────────────────────────────────────────────────────────────

# Minimum character yield we'll accept from digital extraction before
# falling back to OCR. Scripts are typically 50-100+ pages, so anything
# under ~500 chars almost certainly means the PDF is image-only.
MIN_DIGITAL_CHARS = 500


def _extract_digital(path: Path) -> str:
    """
    Try to extract text digitally (no OCR) using pdfplumber, then pdfminer.
    Returns empty string if neither library is available or yields nothing useful.
    """
    # pdfplumber — best for screenplay PDFs (handles columns/tables well)
    try:
        import pdfplumber
        parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return "\n".join(parts)
    except ImportError:
        pass

    # pdfminer fallback
    try:
        from pdfminer.high_level import extract_text as pm_extract
        return pm_extract(str(path)) or ""
    except ImportError:
        return ""


def _extract_ocr(path: Path) -> str:
    """
    OCR fallback for image-based / scanned PDFs.
    Converts each page to an image, then runs Tesseract.
    Requires: pdf2image + pytesseract + a Tesseract binary.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        raise RuntimeError(
            "OCR requires pdf2image and pytesseract.\n"
            "Install with:\n"
            "  pip install pdf2image pytesseract --break-system-packages\n"
            "  # macOS: brew install tesseract poppler\n"
            "  # Linux: sudo apt-get install tesseract-ocr poppler-utils"
        )

    logger.info("PDF appears to be image-based — running OCR (this may take a minute)...")
    pages = convert_from_path(str(path), dpi=200)
    logger.info(f"  OCR: processing {len(pages)} pages...")
    parts = []
    for i, img in enumerate(pages, 1):
        text = pytesseract.image_to_string(img, lang="eng")
        if text.strip():
            parts.append(text)
        if i % 10 == 0:
            logger.info(f"  OCR: {i}/{len(pages)} pages done")
    return "\n".join(parts)


def extract_text_from_pdf(path: Path) -> str:
    """
    Extract text from a PDF.
    Strategy:
      1. Try digital extraction (fast, free, accurate for text-layer PDFs).
      2. If yield is suspiciously low (< MIN_DIGITAL_CHARS), the PDF is likely
         scanned/image-based — fall back to OCR automatically.
    """
    text = _extract_digital(path)

    if len(text.strip()) >= MIN_DIGITAL_CHARS:
        logger.info(f"Digital extraction succeeded ({len(text):,} chars)")
        return text

    if text.strip():
        logger.info(f"Digital extraction yielded only {len(text.strip())} chars — looks image-based. Trying OCR...")
    else:
        logger.info("No text found via digital extraction — PDF is image-based. Running OCR...")

    return _extract_ocr(path)


def extract_text(path: Path) -> str:
    """Extract text from a PDF or plain-text script file."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        logger.info(f"Extracting text from PDF: {path.name}")
        text = extract_text_from_pdf(path)
    elif suffix in (".txt", ".md", ".fountain", ".fdx", ""):
        text = path.read_text(encoding="utf-8", errors="ignore")
    else:
        # Try reading as plain text for unknown extensions
        logger.warning(f"Unknown extension '{suffix}' — attempting plain-text read.")
        text = path.read_text(encoding="utf-8", errors="ignore")

    if not text.strip():
        raise ValueError(
            f"No text could be extracted from '{path}'.\n"
            "  If this is a scanned PDF, ensure tesseract is installed:\n"
            "    macOS: brew install tesseract poppler\n"
            "    Linux: sudo apt-get install tesseract-ocr poppler-utils"
        )

    logger.info(f"Extracted {len(text):,} characters from {path.name}")
    return text


# ─── Show ID ────────────────────────────────────────────────────────────────────

def derive_show_id(path: Path) -> str:
    """Derive a clean show_id from a filename."""
    name = path.stem  # strip extension
    # Replace spaces and special chars with hyphens, lowercase
    name = re.sub(r"[^\w\-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-").lower()
    return name


# ─── Scoring ────────────────────────────────────────────────────────────────────

def load_scoring_config() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(f"Scoring config not found: {CONFIG_FILE}")
    return json.loads(CONFIG_FILE.read_text())


def load_new_dimensions() -> list:
    if not NEW_DIMS_FILE.exists():
        return []
    dims = json.loads(NEW_DIMS_FILE.read_text())
    return [d for d in dims if d.get("name") != "example_dimension"]


BASE_DIMENSIONS = [
    "audience_appeal_marketability",
    "conceptual_hook_clarity",
    "character_appeal_and_long_term_potential",
    "creative_originality_and_boldness",
    "narrative_momentum_engagement",
]


def build_full_prompt(config: dict, new_dims: list) -> str:
    """Full 10-dim prompt: base rubric + new dimensions."""
    rubric_file = Path(config.get("rubric_file", str(RUBRIC_FILE)))
    rubric = rubric_file.read_text()

    if not new_dims:
        return rubric

    new_section = ["\n\n---\n## Additional Dimensions to Score\n",
                   "Score the following NEW dimensions in addition to the 5 above.\n"]
    for i, dim in enumerate(new_dims, 1):
        new_section.append(f"\n### {i}. {dim['display_name']} (1-10)")
        new_section.append(f"**What it measures:** {dim['what_it_measures']}\n")
        new_section.append("**Strong signals (7-10):**")
        for s in dim.get("strong_signals", []):
            new_section.append(f"- {s}")
        new_section.append("\n**Weak signals (1-6):**")
        for s in dim.get("weak_signals", []):
            new_section.append(f"- {s}")
        anchors = dim.get("anchors", {})
        if anchors:
            new_section.append("\n**Scoring anchors:**")
            for rng, ex in anchors.items():
                new_section.append(f"- {rng}: {ex}")
    return rubric + "\n".join(new_section)


def build_output_format(all_dims: list) -> str:
    example = {d: {"score": 7, "reasoning": "one sentence"} for d in all_dims}
    return f"""
## Output Format

Return ONLY valid JSON with this exact structure:
```json
{json.dumps(example, indent=2)}
```

Use these exact JSON keys: {all_dims}
Score each 1-10. Reasoning must be one sentence max.
Return ONLY valid JSON, no other text.
"""


def score_script(show_id: str, text: str, config: dict, new_dims: list) -> dict:
    """Single LLM call — scores all 10 dimensions."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY not set.\n"
            "Run:  export OPENAI_API_KEY=your_key_here"
        )

    import openai
    client = openai.OpenAI(api_key=api_key, timeout=90.0, max_retries=0)

    new_dim_names = [d["name"] for d in new_dims]
    all_dims = BASE_DIMENSIONS + [n for n in new_dim_names if n not in BASE_DIMENSIONS]

    scoring_prompt = build_full_prompt(config, new_dims)
    truncated = text[:MAX_CHARS]

    full_prompt = f"""{scoring_prompt}

---

## Script / Content to Evaluate

**Show ID:** {show_id}

{truncated}

---

{build_output_format(all_dims)}"""

    logger.info(f"Scoring '{show_id}' across {len(all_dims)} dimensions...")
    resp = client.chat.completions.create(
        model=config.get("model", "gpt-4o-mini"),
        messages=[{"role": "user", "content": full_prompt}],
        max_completion_tokens=3000,
    )
    raw = resp.choices[0].message.content.strip()

    if not raw:
        raise ValueError("Empty response from LLM")

    # Clean markdown fences
    for marker in ["```json", "```"]:
        if marker in raw:
            raw = raw.split(marker)[1].split("```")[0].strip()
            break

    if not raw.startswith("{"):
        start, end = raw.find("{"), raw.rfind("}") + 1
        if start != -1 and end > start:
            raw = raw[start:end]
        else:
            raise ValueError(f"No JSON found in LLM response:\n{raw[:300]}")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # LLM sometimes returns slightly malformed JSON (unescaped newlines in
        # reasoning fields, trailing commas, etc.). json_repair handles these.
        try:
            from json_repair import repair_json
            parsed = json.loads(repair_json(raw))
        except Exception as repair_err:
            raise ValueError(
                f"Could not parse LLM response as JSON (even after repair).\n"
                f"Raw response (first 300 chars):\n{raw[:300]}"
            ) from repair_err

    # Normalize
    scores = {}
    for dim in all_dims:
        val = parsed.get(dim, {})
        if isinstance(val, dict):
            scores[dim] = {
                "score":     float(val.get("score", 0)),
                "reasoning": val.get("reasoning", ""),
            }
        elif isinstance(val, (int, float)):
            scores[dim] = {"score": float(val), "reasoning": ""}
        else:
            scores[dim] = {"score": 0.0, "reasoning": "parse_error"}

    return {
        "show_id":       show_id,
        "run_id":        V3_RUN_ID,
        "model":         config.get("model", "gpt-4o-mini"),
        "label_version": "fresh",
        "label":         None,
        "evidence_type": "pilot_script",
        "scored_at":     datetime.now(timezone.utc).isoformat(),
        "scoring":       scores,
        "scoring_mode":  "full_10_dims",
        "status":        "success",
    }


# ─── Entry Point ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="GEM Single-Script Evaluator — score a fresh pilot script and get a report",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 src/gem_eval.py my_pilot.pdf
  python3 src/gem_eval.py my_pilot.txt --show-id "dark-matter-pilot-2026"
  python3 src/gem_eval.py my_pilot.pdf --no-llm --out results/my_report.json
""",
    )
    parser.add_argument("script_file",
                        help="Path to pilot script (.pdf or .txt)")
    parser.add_argument("--show-id", default=None,
                        help="Custom show ID (default: derived from filename)")
    parser.add_argument("--out", default=None,
                        help="Custom output path for JSON report")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip one-line LLM synthesis in report (uses fallback)")
    parser.add_argument("--json-only", action="store_true",
                        help="Write JSON only, suppress stdout report")
    parser.add_argument("--force-rescore", action="store_true",
                        help="Re-score even if a score record already exists")
    args = parser.parse_args()

    script_path = Path(args.script_file)
    if not script_path.exists():
        print(f"ERROR: Script file not found: {script_path}", file=sys.stderr)
        sys.exit(1)

    show_id = args.show_id or derive_show_id(script_path)
    logger.info(f"Show ID: {show_id}")

    # ── Step 1: Score ──────────────────────────────────────────────────────────
    score_path = PER_SCRIPT_DIR / f"{show_id}.json"
    PER_SCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    if score_path.exists() and not args.force_rescore:
        existing = json.loads(score_path.read_text())
        if existing.get("status") == "success":
            logger.info(f"Score record already exists for '{show_id}'. Using cached scores.")
            logger.info(f"  (Use --force-rescore to re-score)")
        else:
            logger.info(f"Existing score record has status={existing.get('status')}. Re-scoring.")
            score_path.unlink()

    if not score_path.exists():
        try:
            text = extract_text(script_path)
        except (ValueError, RuntimeError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

        try:
            config = load_scoring_config()
            new_dims = load_new_dimensions()
            score_record = score_script(show_id, text, config, new_dims)
        except EnvironmentError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"ERROR during scoring: {e}", file=sys.stderr)
            sys.exit(1)

        score_path.write_text(json.dumps(score_record, indent=2))
        logger.info(f"Scores saved → {score_path}")

    # ── Step 2: Report ─────────────────────────────────────────────────────────
    # Import report generator
    sys.path.insert(0, str(BASE_DIR / "src"))
    try:
        import report_generator as rg
    except ImportError as e:
        print(f"ERROR: Could not import report_generator: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        report = rg.build_report(show_id, use_llm=not args.no_llm)
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR building report: {e}", file=sys.stderr)
        sys.exit(1)

    out_path = Path(args.out) if args.out else REPORTS_DIR / f"{show_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))

    if not args.json_only:
        rg.print_report(report)

    print(f"Scores  → {score_path}")
    print(f"Report  → {out_path}")


if __name__ == "__main__":
    main()
