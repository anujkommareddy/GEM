"""
ocr_extract.py — OCR extraction for scanned/image-based PDFs

pdfplumber silently produces empty files for scanned PDFs.
This script detects those and re-extracts using OCR (pdf2image + pytesseract).

Usage:
    # Re-extract all empty txt files, given a folder of PDFs
    python3 src/ocr_extract.py --pdf-dir /path/to/pdfs

    # Re-extract a single PDF
    python3 src/ocr_extract.py --pdf /path/to/parks-and-rec.pdf

    # Just list which extracted_text files are empty (no extraction)
    python3 src/ocr_extract.py --list-empty

    # Re-extract all empties, PDFs must be in data/pdfs/
    python3 src/ocr_extract.py --fix-all

Setup (on your Mac):
    pip install pdf2image pytesseract pymupdf
    brew install tesseract poppler
"""

import argparse
import json
import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

BASE_DIR       = Path(".")
EXTRACTED_DIR  = BASE_DIR / "data/extracted_text"
PDF_DIR        = BASE_DIR / "data/pdfs"

MIN_CHARS = 100  # below this = consider the extraction empty/failed


def is_empty_extraction(txt_path: Path) -> bool:
    if not txt_path.exists():
        return True
    return len(txt_path.read_text(encoding="utf-8", errors="ignore").strip()) < MIN_CHARS


def get_empty_ids() -> list:
    return [
        f.stem for f in EXTRACTED_DIR.glob("*.txt")
        if is_empty_extraction(f)
    ]


def extract_with_pdfplumber(pdf_path: Path) -> str:
    import pdfplumber
    chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            chunks.append(page.extract_text() or "")
    return "\n\n".join(chunks)


def extract_with_pymupdf(pdf_path: Path) -> str:
    """Try pymupdf — sometimes works on PDFs pdfplumber can't read."""
    try:
        import fitz  # pymupdf
        doc = fitz.open(str(pdf_path))
        chunks = []
        for page in doc:
            chunks.append(page.get_text())
        return "\n\n".join(chunks)
    except ImportError:
        return ""


def extract_with_ocr(pdf_path: Path, dpi: int = 300) -> str:
    """Full OCR: convert pages to images, run tesseract."""
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except ImportError:
        logger.error("OCR deps missing. Run: pip install pdf2image pytesseract && brew install tesseract poppler")
        sys.exit(1)

    logger.info(f"  OCR extracting {pdf_path.name} at {dpi}dpi...")
    images = convert_from_path(str(pdf_path), dpi=dpi)
    chunks = []
    for i, img in enumerate(images):
        text = pytesseract.image_to_string(img, config="--psm 6")
        chunks.append(text)
        if (i + 1) % 10 == 0:
            logger.info(f"    Page {i+1}/{len(images)}...")
    return "\n\n".join(chunks)


def extract_best(pdf_path: Path) -> tuple:
    """
    Try extraction methods in order. Return (method_used, text).
    1. pdfplumber (fast, works on text PDFs)
    2. pymupdf (wider compatibility)
    3. OCR via tesseract (slowest, works on image PDFs)
    """
    # 1. pdfplumber
    try:
        text = extract_with_pdfplumber(pdf_path)
        if len(text.strip()) >= MIN_CHARS:
            return "pdfplumber", text
    except Exception as e:
        logger.warning(f"  pdfplumber failed: {e}")

    # 2. pymupdf
    text = extract_with_pymupdf(pdf_path)
    if len(text.strip()) >= MIN_CHARS:
        return "pymupdf", text

    # 3. OCR
    text = extract_with_ocr(pdf_path)
    if len(text.strip()) >= MIN_CHARS:
        return "ocr_tesseract", text

    return "failed", ""


def process_pdf(pdf_path: Path, force: bool = False) -> bool:
    """Extract text from one PDF, write to extracted_text/. Returns True on success."""
    txt_path = EXTRACTED_DIR / f"{pdf_path.stem}.txt"

    if not force and not is_empty_extraction(txt_path):
        logger.info(f"  Already has good text ({txt_path.stat().st_size} bytes), skipping")
        return True

    method, text = extract_best(pdf_path)

    if not text.strip():
        logger.warning(f"  FAILED — no text extracted from {pdf_path.name}")
        return False

    txt_path.write_text(text, encoding="utf-8")
    logger.info(f"  ✓ {pdf_path.name} → {len(text):,} chars ({method})")
    return True


def cmd_list_empty():
    empty = get_empty_ids()
    print(f"\nEmpty extractions: {len(empty)}")
    for sid in empty:
        print(f"  {sid}")
    print(f"\nTo fix: python3 src/ocr_extract.py --pdf-dir /path/to/your/pdfs")


def cmd_fix_single(pdf_path: Path):
    logger.info(f"Processing: {pdf_path}")
    success = process_pdf(pdf_path, force=True)
    if success:
        txt = (EXTRACTED_DIR / f"{pdf_path.stem}.txt").read_text()
        print(f"\nExtracted {len(txt):,} chars. Preview:")
        print(txt[:500])
    else:
        print("Extraction failed.")


def cmd_fix_all_from_dir(pdf_dir: Path):
    """Process all PDFs in a directory whose extracted_text is empty."""
    empty_ids = set(get_empty_ids())
    pdf_files = list(pdf_dir.glob("*.pdf"))

    # Find PDFs that match empty extraction IDs
    to_process = [p for p in pdf_files if p.stem in empty_ids]
    no_pdf_for = [sid for sid in empty_ids if not (pdf_dir / f"{sid}.pdf").exists()]

    print(f"\nEmpty extractions: {len(empty_ids)}")
    print(f"PDFs found in {pdf_dir}: {len(to_process)}")
    print(f"Empty IDs with no matching PDF: {len(no_pdf_for)}")

    if no_pdf_for:
        print("\nNo PDF found for:")
        for sid in no_pdf_for[:10]:
            print(f"  {sid}")
        if len(no_pdf_for) > 10:
            print(f"  ... and {len(no_pdf_for)-10} more")

    if not to_process:
        print("\nNo matching PDFs to process.")
        return

    print(f"\nProcessing {len(to_process)} PDFs...")
    success, failed = 0, 0
    for i, pdf_path in enumerate(to_process, 1):
        logger.info(f"[{i}/{len(to_process)}] {pdf_path.name}")
        if process_pdf(pdf_path, force=True):
            success += 1
        else:
            failed += 1

    print(f"\nDone: {success} succeeded, {failed} failed")
    print(f"\nNow re-run scoring to pick up newly extracted scripts:")
    print(f"  python3 src/score_run.py --run v3_expanded")
    print(f"  (resume-safe — only scores the newly extracted ones)")


def main():
    parser = argparse.ArgumentParser(description="OCR extraction for scanned PDFs")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list-empty", action="store_true",
                       help="List all empty extracted_text files")
    group.add_argument("--pdf", type=Path,
                       help="Extract a single PDF file")
    group.add_argument("--pdf-dir", type=Path,
                       help="Extract all empty-extraction PDFs found in this directory")
    group.add_argument("--fix-all", action="store_true",
                       help="Extract all empties, looking for PDFs in data/pdfs/")
    args = parser.parse_args()

    if args.list_empty:
        cmd_list_empty()
    elif args.pdf:
        if not args.pdf.exists():
            print(f"File not found: {args.pdf}")
            sys.exit(1)
        cmd_fix_single(args.pdf)
    elif args.pdf_dir:
        if not args.pdf_dir.exists():
            print(f"Directory not found: {args.pdf_dir}")
            sys.exit(1)
        cmd_fix_all_from_dir(args.pdf_dir)
    elif args.fix_all:
        if not PDF_DIR.exists() or not any(PDF_DIR.glob("*.pdf")):
            print(f"No PDFs found in {PDF_DIR}. Use --pdf-dir to specify location.")
            sys.exit(1)
        cmd_fix_all_from_dir(PDF_DIR)


if __name__ == "__main__":
    main()
