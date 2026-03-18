#!/usr/bin/env python3
"""
pdf_to_txt_v2.py — Convert PDFs to .txt using PyPDF2 (no cryptography dependency).
Skips encrypted PDFs gracefully.
"""

import pathlib, sys
from PyPDF2 import PdfReader

ROOT = pathlib.Path(__file__).resolve().parent
SRC  = ROOT / "pdf_backup"
DST  = ROOT / "txt_raw"
DST.mkdir(exist_ok=True)

pdfs = sorted(SRC.glob("*.pdf"))
if not pdfs:
    # fallback to main dir
    pdfs = sorted(ROOT.glob("*.pdf"))
if not pdfs:
    sys.exit("No PDF files found.")

ok = 0
skipped = 0

for pdf_path in pdfs:
    txt_path = DST / f"{pdf_path.stem}.txt"
    if txt_path.exists():
        ok += 1
        continue
    try:
        reader = PdfReader(pdf_path)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                print(f"✗ SKIP (encrypted): {pdf_path.name}")
                skipped += 1
                continue
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        if pages:
            txt_path.write_text("\n\n".join(pages))
            ok += 1
            print(f"✓ {pdf_path.name}")
        else:
            print(f"✗ SKIP (no text): {pdf_path.name}")
            skipped += 1
    except Exception as e:
        print(f"✗ SKIP ({e.__class__.__name__}): {pdf_path.name}")
        skipped += 1

print(f"\nDone. {ok} converted, {skipped} skipped. Output: {DST}")
