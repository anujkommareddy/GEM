#!/usr/bin/env python3
"""Re-evaluate scripts that got zero scores due to JSON parsing failures.

Deletes their per-script JSONs so the main eval loop picks them up on resume.
Only targets scripts where the extracted text is good but scoring failed.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def find_broken_scripts():
    """Find scripts with 0 or ~1.0 scores that have good extracted text."""
    per_script = Path("data/results/live/per_script")
    broken = []

    for f in sorted(per_script.glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except:
            broken.append(f)
            continue

        if d.get("status") != "success":
            continue

        agg = d.get("aggregated", {})
        wa = agg.get("weighted_average", -1)

        if wa > 1.1:
            continue  # Normal score, skip

        # Check if text is good
        sid = d.get("script_id", f.stem)
        text_file = Path(f"data/extracted_text/{sid}.txt")
        if not text_file.exists():
            continue

        text = text_file.read_text()
        if len(text) < 5000:
            continue  # Too short, probably bad extraction
        if "Script provided for educational" in text[:1000]:
            continue  # Watermark garbage, can't fix

        broken.append(f)

    return broken


def main():
    broken = find_broken_scripts()
    print(f"Found {len(broken)} scripts to re-evaluate")

    if not broken:
        print("Nothing to fix!")
        return

    # Delete their per-script JSONs
    script_ids = []
    for f in broken:
        sid = f.stem
        script_ids.append(sid)
        f.unlink()
        print(f"  Deleted: {f.name}")

    print(f"\nDeleted {len(broken)} broken result files.")
    print(f"Now run: python3 main.py run-eval")
    print(f"The eval loop will skip already-done scripts and only re-evaluate these {len(broken)}.")


if __name__ == "__main__":
    main()
