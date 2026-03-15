#!/usr/bin/env python3
"""
pdf_to_txt.py
• Converts every PDF in the current folder (pdf_raw) to .txt
• Writes the .txt files (same names) into ./txt_raw/
"""

import pdfplumber, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
SRC  = ROOT                                # this folder holds the PDFs
DST  = ROOT / "txt_raw"                    # destination
DST.mkdir(exist_ok=True)

pdfs = sorted(SRC.glob("*.pdf"))
if not pdfs:
    sys.exit("No PDF files found in this folder.")

for pdf_path in pdfs:
    txt_path = DST / f"{pdf_path.stem}.txt"
    text_chunks = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text_chunks.append(page.extract_text() or "")
    txt_path.write_text("\n\n".join(text_chunks))
    print(f"✓ {pdf_path.name}  →  txt_raw/{txt_path.name}")

print(f"\nDone. {len(pdfs)} PDFs converted to {DST}")
