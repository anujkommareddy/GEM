#!/usr/bin/env python3
"""Fix benchmark ID mismatches and evaluate missing scripts."""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ID mapping: mangled benchmark ID -> actual PDF/text filename
ID_FIXES = {
    "American_Horror_StoryPilot_fdb3aedd_american-horror-story-101-pilot-2011": "american-horror-story-101-pilot-2011",
    "House_of_CardsChapter_1_91033b0e_house-of-card-101-chapter-1-2013": "house-of-card-101-chapter-1-2013",
    "Silicon_ValleyMinimum_Viable_Product_693297d6_silicon-valley-101-minimum-viable-product-2014": "silicon-valley-101-minimum-viable-product-2014",
    "SuccessionCelebration_e606314f_succession-101-celebration-2018": "succession-101-celebration-2018",
    "The_Handmaids_TaleOffred_8a135755_the-handmaids-tale-1x01-offred-2017": "the-handmaids-tale-1x01-offred-2017",
}

# Scripts with extracted text but not in benchmark — add as unlabeled
UNLABELED_TO_ADD = [
    "Counterpart_1x01_-_Pilot",
    "Hannibal_1x01_-_Pilot",
    "See_1x01_-_Godflame",
    "The_Bridge_1x01_-_Pilot",
    "The_Killing_1x01_-_Pilot",
    "The_OA_1x01_-_Pilot",
    "bloodline-101-part-1-2015",
    "mr-robot-101-eps1-0-hellofriend-mov-2015",
]
# Note: AHS and Succession are already handled by ID_FIXES (they'll become winner entries)

def main():
    benchmark_file = Path("data/benchmark/benchmark.jsonl")

    # Load benchmark
    entries = {}
    with open(benchmark_file) as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                entries[d["script_id"]] = d

    print(f"Loaded {len(entries)} benchmark entries")

    # Fix mangled IDs
    fixed = 0
    for old_id, new_id in ID_FIXES.items():
        if old_id in entries:
            entry = entries.pop(old_id)
            entry["script_id"] = new_id
            entry["original_benchmark_id"] = old_id
            entries[new_id] = entry
            fixed += 1
            print(f"  Fixed: {old_id} -> {new_id} (outcome={entry.get('outcome')})")
        else:
            print(f"  WARN: {old_id} not found in benchmark")

    print(f"Fixed {fixed} mangled IDs")

    # Add unlabeled scripts
    added = 0
    for sid in UNLABELED_TO_ADD:
        if sid not in entries:
            entries[sid] = {
                "script_id": sid,
                "title": None,
                "extracted_text_path": f"data/extracted_text/{sid}.txt",
                "label": None,
                "outcome": None,
                "human_score": None,
                "notes": "Added from extracted PDFs (no label)",
                "metadata": None,
            }
            added += 1
            print(f"  Added unlabeled: {sid}")

    print(f"Added {added} unlabeled scripts")

    # Save updated benchmark
    with open(benchmark_file, "w") as f:
        for entry in sorted(entries.values(), key=lambda e: e["script_id"]):
            f.write(json.dumps(entry) + "\n")

    print(f"Saved {len(entries)} entries to {benchmark_file}")

    # Now evaluate just the new/fixed scripts
    scripts_to_eval = list(ID_FIXES.values()) + UNLABELED_TO_ADD

    # Check which ones already have results
    per_script_dir = Path("data/results/live/per_script")
    already_done = set()
    for f in per_script_dir.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            if d.get("status") == "success":
                already_done.add(d.get("script_id"))
        except:
            pass

    to_eval = [s for s in scripts_to_eval if s not in already_done]
    print(f"\nNeed to evaluate: {len(to_eval)} scripts")

    if not to_eval:
        print("All scripts already evaluated!")
        return

    # Run evaluation on just these scripts
    from config import Config
    from evaluator import ScreenplayEvaluator
    from ingestion import PDFIngester
    from live_output import LiveOutputWriter
    from benchmark import Benchmark

    config = Config("./config")
    model = config.get("models.default")
    evaluator = ScreenplayEvaluator(config, model)
    ingester = PDFIngester(config.get_path("pdf_source"), config.get_path("extracted_text"))
    benchmark = Benchmark(benchmark_file)

    # Use existing live output dir
    live = LiveOutputWriter(
        output_dir=config.get_path("experiment_dir"),
        model=config.get(f"models.{model}.model", model),
        run_id="fix_missing",
    )
    live.set_total_scripts(len(to_eval))

    success = 0
    fail = 0
    for i, sid in enumerate(to_eval, 1):
        text = ingester.get_script_text(sid)
        if not text:
            print(f"  [{i}/{len(to_eval)}] {sid} — no text found, skipping")
            continue

        print(f"  [{i}/{len(to_eval)}] {sid}...")
        entry = benchmark.get_entry(sid)
        result = evaluator.evaluate(sid, text)
        live.record_result(result, entry)

        if result.get("status") == "success":
            success += 1
            score = result.get("aggregated", {}).get("weighted_average", "?")
            cat = result.get("aggregated", {}).get("recommendation_category", "?")
            print(f"    -> {score}/10 ({cat})")
        else:
            fail += 1
            print(f"    -> ERROR: {result.get('error', 'unknown')}")

    live.finalize()
    print(f"\nDone: {success} success, {fail} failed")


if __name__ == "__main__":
    main()
