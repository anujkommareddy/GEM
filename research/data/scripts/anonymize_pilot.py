#!/usr/bin/env python3
"""
anonymize_pilot.py
──────────────────
• Reads every .txt in txt_raw/
• Writes anonymized copies (same filenames) into txt_clean/

Anonymization logic
1. Remove title page (everything before first INT./EXT.)
2. Mask ALL-CAPS character headings → CHARACTER
3. Replace show title (first line ALL-CAPS) → SHOW_TITLE
4. Strip explicit network/streamer mentions like [NBC], (NETFLIX), etc.
"""

import re, pathlib, sys

ROOT    = pathlib.Path(__file__).resolve().parent
SRC_DIR = ROOT / "txt_raw"
DST_DIR = ROOT / "txt_clean"
DST_DIR.mkdir(exist_ok=True)

if not SRC_DIR.exists():
    sys.exit(f"Source folder {SRC_DIR} does not exist.")

txt_files = sorted(SRC_DIR.glob("*.txt"))
if not txt_files:
    sys.exit(f"No .txt files found in {SRC_DIR}")

slug = re.compile(r'^\s*(INT\.|EXT\.)')                      # first slug
caps = re.compile(r'^\s{0,20}[A-Z][A-Z0-9 \-]{2,}$')         # centered CAPS
net  = re.compile(r'[\[(](NBC|HBO|NETFLIX|FX|FOX|CBS|ABC|HULU|PARAMOUNT\+?)[\])]?', re.I)

def anonymize(src: pathlib.Path, dst: pathlib.Path):
    lines = src.read_text(errors="ignore").splitlines()

    # 1 ─ drop everything before first slug
    start = next((i for i, l in enumerate(lines) if slug.match(l)), 0)
    body  = lines[start:]

    # 2 ─ ALL-CAPS names (≤3 words)
    names = {l.strip() for l in body if caps.match(l)}
    names = {n for n in names if len(n.split()) <= 3}

    # 3 ─ guess title from line 0 (uppercase letters only)
    title_caps = re.sub(r'[^A-Z]', '', lines[0].upper())[:20]
    title_re   = re.compile(r'\b' + re.escape(title_caps) + r'\b') if len(title_caps) >= 3 else None

    out = []
    for ln in body:
        # mask standalone headings
        if ln.strip() in names:
            out.append(ln.replace(ln.strip(), "CHARACTER")); continue

        # inline replacements
        for n in names:
            ln = re.sub(r'\b' + re.escape(n) + r'\b', "CHARACTER", ln)
        if title_re:
            ln = title_re.sub("SHOW_TITLE", ln)

        # remove network tags
        ln = net.sub("", ln)

        out.append(ln)

    dst.write_text("\n".join(out))

# ─── batch run ──────────────────────────────────────────────────────────
for txt in txt_files:
    dst_file = DST_DIR / txt.name
    anonymize(txt, dst_file)
    print(f"✓ {txt.name}  →  txt_clean/")

print(f"\nDone. {len(txt_files)} scripts anonymized to {DST_DIR}")
