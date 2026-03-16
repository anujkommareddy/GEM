#!/usr/bin/env python3
"""GEM Research Pipeline — CLI entry point.

Usage:
    python cli.py ingest                               Ingest and link data
    python cli.py labels                               Inspect label schemes
    python cli.py facets                               List the 5 core facets
    python cli.py analyze [--mock] [--provider X] [--model Y]  Run script analysis
    python cli.py test                                 Run hypothesis testing
    python cli.py report                               Generate full report
    python cli.py status                               Show pipeline status

Environment variables:
    OPENAI_API_KEY       Required for OpenAI provider
    ANTHROPIC_API_KEY    Required for Anthropic provider
"""

from __future__ import annotations

import json
import os
import sys

# Ensure research/ is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Default paths
SHEET_PATH = "data/sheets/master_pilots_list.csv"
SCRIPTS_DIR = "data/scripts/txt_raw"
DATASET_PATH = "data/linked_dataset.json"
ANALYSES_DIR = "output/analyses"
OUTPUT_DIR = "output"


def _parse_flag(args: list[str], flag: str, default: str | None = None) -> tuple[str | None, list[str]]:
    """Extract --flag value from args list. Returns (value, remaining_args)."""
    remaining = []
    value = default
    i = 0
    while i < len(args):
        if args[i] == flag and i + 1 < len(args):
            value = args[i + 1]
            i += 2
        else:
            remaining.append(args[i])
            i += 1
    return value, remaining


def cmd_ingest(args: list[str]):
    """Ingest sheet + scripts, produce linked dataset."""
    from ingest import link_data, load_scripts, load_sheet, save_linked_dataset

    sheet_path = args[0] if args else SHEET_PATH
    scripts_dir = args[1] if len(args) > 1 else SCRIPTS_DIR

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

    print("\nLinking shows to scripts...")
    records = link_data(shows, scripts, scripts_dir)

    os.makedirs("data", exist_ok=True)
    save_linked_dataset(records, DATASET_PATH)

    with_scripts = sum(1 for r in records if r.scripts)
    winners_with = sum(1 for r in records if r.scripts and r.show.raw_label.lower() == "winner")
    losers_with = sum(1 for r in records if r.scripts and r.show.raw_label.lower() == "loser")
    print(f"\n  Summary: {with_scripts} shows with scripts ({winners_with} winners, {losers_with} losers)")
    print(f"  Dataset saved to {DATASET_PATH}")
    print(f"\n  Next: python cli.py labels")


def cmd_labels(args: list[str]):
    """Show label distribution and scheme summaries."""
    from ingest import load_linked_dataset
    from labels import build_default_schemes, inspect_labels, scheme_summary

    path = args[0] if args else DATASET_PATH
    records = load_linked_dataset(path)

    print("Raw label distribution:")
    for label, count in inspect_labels(records).items():
        print(f"  {label}: {count}")

    with_scripts = sum(1 for r in records if r.scripts)
    print(f"\nShows with scripts: {with_scripts}")

    print("\nLabel scheme summaries:")
    for scheme in build_default_schemes():
        s = scheme_summary(records, scheme)
        print(f"\n  {s['scheme']}: {s['description']}")
        print(f"    Winners: {s['winners']} ({s['winner_pct']}%)")
        print(f"    Losers:  {s['losers']} ({s['loser_pct']}%)")
        print(f"    Excluded: {s['excluded']}")


def cmd_facets(args: list[str]):
    """List all core facets."""
    from factors import get_default_facets

    facets = get_default_facets()
    print(f"Core Facets ({len(facets)}):\n")
    for f in facets:
        print(f"  {f.name}")
        print(f"    {f.description}")
        print(f"    Strong: {f.strong_signals[:80]}...")
        print(f"    Weak:   {f.weak_signals[:80]}...")
        print()


def cmd_analyze(args: list[str]):
    """Run script analysis."""
    from analyze import analyze_batch
    from ingest import load_linked_dataset, load_scripts

    use_mock = "--mock" in args
    args = [a for a in args if a != "--mock"]

    provider, args = _parse_flag(args, "--provider", "openai")
    model, args = _parse_flag(args, "--model")

    dataset_path = args[0] if args else DATASET_PATH
    scripts_dir = args[1] if len(args) > 1 else SCRIPTS_DIR

    records = load_linked_dataset(dataset_path)

    # Re-attach script text (not stored in linked dataset)
    scripts = load_scripts(scripts_dir)
    script_map = {s.filename: s for s in scripts}
    for record in records:
        for i, rs in enumerate(record.scripts):
            if rs.filename in script_map:
                record.scripts[i] = script_map[rs.filename]

    os.makedirs(ANALYSES_DIR, exist_ok=True)
    results = analyze_batch(
        records,
        output_dir=ANALYSES_DIR,
        use_mock=use_mock,
        provider=provider,
        model=model,
    )
    print(f"\nResults saved to {ANALYSES_DIR}/")
    print(f"\n  Next: python cli.py test")


def cmd_test(args: list[str]):
    """Run hypothesis testing."""
    from analyze import load_analyses
    from hypothesis import test_stability
    from ingest import load_linked_dataset
    from labels import build_default_schemes

    dataset_path = args[0] if args else DATASET_PATH
    analyses_dir = args[1] if len(args) > 1 else ANALYSES_DIR

    records = load_linked_dataset(dataset_path)
    analyses = load_analyses(analyses_dir)

    print(f"Records: {len(records)} | Analyses: {len(analyses)}\n")

    schemes = build_default_schemes()
    stability = test_stability(records, analyses, schemes)

    print("Facet Stability Results:")
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

    dataset_path = args[0] if args else DATASET_PATH
    analyses_dir = args[1] if len(args) > 1 else ANALYSES_DIR
    output_dir = args[2] if len(args) > 2 else OUTPUT_DIR

    records = load_linked_dataset(dataset_path)
    analyses = load_analyses(analyses_dir)

    print(f"Records: {len(records)} | Analyses: {len(analyses)}\n")

    report = generate_report(records, analyses, output_dir=output_dir)

    print("\nRECOMMENDATIONS:")
    for r in report.recommendations:
        print(f"  -> {r}")


def cmd_status(args: list[str]):
    """Show pipeline status."""
    from providers import DEFAULT_MODELS

    checks = [
        (SHEET_PATH, "Sheet data (CSV)"),
        (SCRIPTS_DIR, "Script files"),
        (DATASET_PATH, "Linked dataset"),
        (ANALYSES_DIR, "Analysis results"),
        (f"{OUTPUT_DIR}/report.json", "JSON report"),
        (f"{OUTPUT_DIR}/report.txt", "Text report"),
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

    print("\nProvider config:")
    for p, m in DEFAULT_MODELS.items():
        env_var = "OPENAI_API_KEY" if p == "openai" else "ANTHROPIC_API_KEY"
        has_key = bool(os.environ.get(env_var))
        status = "configured" if has_key else "NOT SET"
        print(f"  {p}: {m} [{env_var}: {status}]")

    print("\nNext steps:")
    if not os.path.exists(DATASET_PATH):
        print("  1. Run: python cli.py ingest")
    elif not os.path.exists(ANALYSES_DIR) or not os.listdir(ANALYSES_DIR):
        print("  1. Run: python cli.py analyze [--mock for testing]")
    elif not os.path.exists(f"{OUTPUT_DIR}/report.json"):
        print("  1. Run: python cli.py report")
    else:
        print("  Pipeline complete! Review output/report.txt")


# Keep old command name working
cmd_factors = cmd_facets

COMMANDS = {
    "ingest": cmd_ingest,
    "labels": cmd_labels,
    "facets": cmd_facets,
    "factors": cmd_facets,  # backward compat
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
