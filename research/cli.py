#!/usr/bin/env python3
"""GEM Research Pipeline — CLI entry point.

Usage:
    python cli.py ingest <sheet_path> [scripts_dir]   Ingest and link data
    python cli.py labels [dataset_path]                Inspect label schemes
    python cli.py factors                              List candidate factors
    python cli.py analyze [dataset_path] [--mock]      Run script analysis
    python cli.py test [dataset_path] [analyses_dir]   Run hypothesis testing
    python cli.py report [dataset_path] [analyses_dir] Generate full report
    python cli.py status                               Show pipeline status
"""

from __future__ import annotations

import json
import os
import sys

# Ensure research/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def cmd_ingest(args: list[str]):
    """Ingest sheet + scripts, produce linked dataset."""
    from ingest import link_data, load_scripts, load_sheet, save_linked_dataset

    if not args:
        print("Usage: python cli.py ingest <sheet_path> [scripts_dir]")
        print("\n  sheet_path   CSV/TSV/JSON export of your labeled Google Sheet")
        print("  scripts_dir  Directory with script files (default: data/scripts/)")
        sys.exit(1)

    sheet_path = args[0]
    scripts_dir = args[1] if len(args) > 1 else "data/scripts"

    print(f"Loading sheet: {sheet_path}")
    shows = load_sheet(sheet_path)
    print(f"  {len(shows)} shows loaded")

    labels: dict[str, int] = {}
    for s in shows:
        key = s.raw_label.lower().strip()
        labels[key] = labels.get(key, 0) + 1
    print(f"  Labels: {labels}")

    print(f"\nLoading scripts: {scripts_dir}")
    scripts = load_scripts(scripts_dir)
    print(f"  {len(scripts)} scripts loaded")

    print("\nLinking...")
    records = link_data(shows, scripts)

    os.makedirs("data", exist_ok=True)
    save_linked_dataset(records, "data/linked_dataset.json")


def cmd_labels(args: list[str]):
    """Show label distribution and scheme summaries."""
    from ingest import load_linked_dataset
    from labels import build_default_schemes, inspect_labels, scheme_summary

    path = args[0] if args else "data/linked_dataset.json"
    records = load_linked_dataset(path)

    print("Raw label distribution:")
    for label, count in inspect_labels(records).items():
        print(f"  {label}: {count}")

    print("\nLabel scheme summaries:")
    for scheme in build_default_schemes():
        s = scheme_summary(records, scheme)
        print(f"\n  {s['scheme']}: {s['description']}")
        print(f"    Winners: {s['winners']} ({s['winner_pct']}%)")
        print(f"    Losers:  {s['losers']} ({s['loser_pct']}%)")
        print(f"    Excluded: {s['excluded']}")


def cmd_factors(args: list[str]):
    """List all candidate factors."""
    from factors import get_default_factors

    factors = get_default_factors()
    print(f"Candidate Factors ({len(factors)}):\n")
    for f in factors:
        print(f"  {f.name}")
        print(f"    {f.description}")
        print(f"    Why: {f.why_it_matters[:100]}...")
        print()


def cmd_analyze(args: list[str]):
    """Run script analysis."""
    from analyze import analyze_batch
    from ingest import load_linked_dataset, load_scripts

    use_mock = "--mock" in args
    args = [a for a in args if a != "--mock"]

    dataset_path = args[0] if args else "data/linked_dataset.json"
    scripts_dir = args[1] if len(args) > 1 else "data/scripts"

    records = load_linked_dataset(dataset_path)

    # Re-attach script text
    scripts = load_scripts(scripts_dir)
    script_map = {s.filename: s for s in scripts}
    for record in records:
        for i, rs in enumerate(record.scripts):
            if rs.filename in script_map:
                record.scripts[i] = script_map[rs.filename]

    os.makedirs("output/analyses", exist_ok=True)
    analyze_batch(records, use_mock=use_mock)


def cmd_test(args: list[str]):
    """Run hypothesis testing."""
    from analyze import load_analyses
    from hypothesis import test_stability
    from ingest import load_linked_dataset
    from labels import build_default_schemes

    dataset_path = args[0] if args else "data/linked_dataset.json"
    analyses_dir = args[1] if len(args) > 1 else "output/analyses"

    records = load_linked_dataset(dataset_path)
    analyses = load_analyses(analyses_dir)

    print(f"Records: {len(records)} | Analyses: {len(analyses)}\n")

    schemes = build_default_schemes()
    stability = test_stability(records, analyses, schemes)

    print("Factor Stability Results:")
    print("=" * 60)
    for r in stability:
        status = "STABLE" if r.stable else "UNSTABLE"
        direction = "winners higher" if r.mean_separation > 0 else "losers higher"
        print(f"\n  {r.factor_name}: {status}")
        print(f"    Separation: {r.mean_separation:+.3f} ({direction})")
        for scheme, sep in r.separations.items():
            print(f"      {scheme}: {sep:+.3f}")


def cmd_report(args: list[str]):
    """Generate full report."""
    from analyze import load_analyses
    from ingest import load_linked_dataset
    from report import generate_report

    dataset_path = args[0] if args else "data/linked_dataset.json"
    analyses_dir = args[1] if len(args) > 1 else "output/analyses"
    output_dir = args[2] if len(args) > 2 else "output"

    records = load_linked_dataset(dataset_path)
    analyses = load_analyses(analyses_dir)

    print(f"Records: {len(records)} | Analyses: {len(analyses)}\n")

    report = generate_report(records, analyses, output_dir=output_dir)

    print("\nRECOMMENDATIONS:")
    for r in report.recommendations:
        print(f"  -> {r}")


def cmd_status(args: list[str]):
    """Show pipeline status."""
    checks = [
        ("data/sheets/", "Sheet data directory"),
        ("data/scripts/", "Script files directory"),
        ("data/linked_dataset.json", "Linked dataset"),
        ("output/analyses/", "Analysis results"),
        ("output/report.json", "JSON report"),
        ("output/report.txt", "Text report"),
    ]

    print("GEM Research Pipeline — Status\n")
    for path, desc in checks:
        if os.path.exists(path):
            if os.path.isdir(path):
                count = len([f for f in os.listdir(path) if not f.startswith(".")])
                print(f"  [OK] {desc}: {path} ({count} files)")
            else:
                size = os.path.getsize(path)
                print(f"  [OK] {desc}: {path} ({size:,} bytes)")
        else:
            print(f"  [--] {desc}: {path} (not found)")

    print("\nNext steps:")
    if not os.path.exists("data/linked_dataset.json"):
        print("  1. Export your Google Sheet as CSV to data/sheets/")
        print("  2. Place script files in data/scripts/")
        print("  3. Run: python cli.py ingest data/sheets/<your-file>.csv")
    elif not os.path.exists("output/analyses"):
        print("  1. Run: python cli.py analyze [--mock for testing]")
    elif not os.path.exists("output/report.json"):
        print("  1. Run: python cli.py report")
    else:
        print("  Pipeline complete! Review output/report.txt")


COMMANDS = {
    "ingest": cmd_ingest,
    "labels": cmd_labels,
    "factors": cmd_factors,
    "analyze": cmd_analyze,
    "test": cmd_test,
    "report": cmd_report,
    "status": cmd_status,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1]
    if command not in COMMANDS:
        print(f"Unknown command: {command}")
        print(f"Available: {', '.join(COMMANDS.keys())}")
        sys.exit(1)

    # Change to research/ directory for relative paths
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    COMMANDS[command](sys.argv[2:])
