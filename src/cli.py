"""Command-line interface for GEM autoresearch."""

import argparse
import json
import logging
from pathlib import Path
import sys

from config import Config
from ingestion import PDFIngester
from benchmark import Benchmark


def setup_logging(level=logging.INFO):
    """Set up logging."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def ingest_pdfs(args):
    """Ingest PDFs from source directory."""
    try:
        config = Config(args.config_dir)
        pdf_source = Path(args.pdf_source) if args.pdf_source else config.get_path("pdf_source")
        output_dir = config.get_path("extracted_text")

        ingester = PDFIngester(pdf_source, output_dir)
        metadata = ingester.ingest_all(skip_existing=args.skip_existing)

        print(f"\n✓ Ingested {len(metadata)} scripts")
        print(f"  Extracted text saved to: {output_dir}")
        print(f"  Metadata saved to: {output_dir / 'metadata.jsonl'}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def build_benchmark(args):
    """Build benchmark dataset from ingested PDFs."""
    try:
        config = Config(args.config_dir)
        from research_loop import ResearchLoop
        loop = ResearchLoop(config)

        benchmark = loop.setup_benchmark(
            pdf_source=args.pdf_source,
            labels_csv=args.labels_csv,
        )

        stats = benchmark.get_stats()
        print(f"\n✓ Benchmark created: {stats['total_entries']} scripts")
        print(f"  Labeled: {stats['labeled_entries']}")
        print(f"  Unlabeled: {stats['unlabeled_entries']}")
        print(f"  Location: {config.get_path('benchmark_file')}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def run_eval(args):
    """Run evaluation on benchmark."""
    try:
        config = Config(args.config_dir)
        from research_loop import ResearchLoop
        loop = ResearchLoop(config)
        benchmark = Benchmark(config.get_path("benchmark_file"))

        model = args.model or config.get("models.default")
        script_ids = args.script_ids.split(",") if args.script_ids else None

        live_dir = config.get_path("experiment_dir") / "live"
        print(f"\n  Live outputs → {live_dir}/")
        print(f"  Monitor progress:  cat {live_dir}/latest_summary.md")
        print(f"  Watch TSV:         tail -f {live_dir}/results.tsv")
        print(f"  Leaderboard:       cat {live_dir}/leaderboard.json")
        print(f"  Per-script JSONs:  ls {live_dir}/per_script/\n")

        results = loop.run_evaluation(benchmark, script_ids=script_ids, model=model)

        print(f"\n✓ Evaluation complete: {len(results)} scripts")
        successful = [r for r in results if r.get("status") == "success"]
        print(f"  Successful: {len(successful)}")
        print(f"  Failed: {len(results) - len(successful)}")
        print(f"  Results: {live_dir}/")
        print(f"  Summary: {live_dir}/latest_summary.md")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def show_results(args):
    """Show experiment results."""
    try:
        config = Config(args.config_dir)
        from metrics import MetricsTracker
        metrics = MetricsTracker(config.get_path("results_log"))
        results = metrics.load_results()

        if not results:
            print("No results found")
            return

        print(f"\n{'Timestamp':<22} {'Exp ID':<18} {'Model':<8} {'Scripts':<8} {'Status':<10}")
        print("-" * 70)

        for r in results[-20:]:  # Show last 20
            print(
                f"{r.get('timestamp', ''):<22} "
                f"{r.get('experiment_id', ''):<18} "
                f"{r.get('model', ''):<8} "
                f"{r.get('scripts_evaluated', ''):<8} "
                f"{r.get('keep_discard', ''):<10}"
            )

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def iterate(args):
    """Run auto-research improvement loop."""
    try:
        config = Config(args.config_dir)
        from iterate import IterationOrchestrator
        from auto_proposer import AutoProposer

        orchestrator = IterationOrchestrator(config)

        # Show suggestions
        print("\n" + "=" * 80)
        print("AUTO-RESEARCH IMPROVEMENT LOOP")
        print("=" * 80)
        AutoProposer.suggestions_for_baseline()

        # Create sample if needed (not needed for auto)
        if not args.auto:
            print(f"\nCreating stratified sample ({args.sample_size} scripts)...")
            orchestrator.create_sample(args.sample_size)

        # Run improvement loop
        print(f"\nStarting improvement loop...")
        orchestrator.run_improvement_loop(
            max_iterations=args.max_iterations, sample_only=args.sample_only, auto=args.auto
        )

        # Show summary
        print("\n" + "=" * 80)
        print("IMPROVEMENT LOOP COMPLETE")
        print("=" * 80)
        exp_log = config.get_path("experiment_dir") / "experiments.jsonl"
        print(f"\nExperiment log: {exp_log}")
        print(f"Full summary: {config.get_path('experiment_dir') / 'experiment_summary.json'}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main CLI entry point."""
    setup_logging()

    parser = argparse.ArgumentParser(
        description="GEM Autoresearch: Iterative screenplay evaluator",
    )
    parser.add_argument(
        "--config-dir",
        default="./config",
        help="Config directory (default: ./config)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # ingest-pdfs
    ingest_parser = subparsers.add_parser("ingest-pdfs", help="Ingest PDFs from folder")
    ingest_parser.add_argument(
        "--pdf-source",
        help="PDF source directory (default: from config)",
    )
    ingest_parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip PDFs that already have extracted text",
    )
    ingest_parser.set_defaults(func=ingest_pdfs)

    # build-benchmark
    bench_parser = subparsers.add_parser("build-benchmark", help="Build benchmark dataset")
    bench_parser.add_argument("--pdf-source", help="PDF source directory")
    bench_parser.add_argument("--labels-csv", help="CSV file with labels")
    bench_parser.set_defaults(func=build_benchmark)

    # run-eval
    eval_parser = subparsers.add_parser("run-eval", help="Run evaluation on benchmark")
    eval_parser.add_argument(
        "--model",
        choices=["claude", "openai"],
        help="Model to use (default: from config)",
    )
    eval_parser.add_argument(
        "--script-ids",
        help="Comma-separated script IDs to evaluate (default: all)",
    )
    eval_parser.set_defaults(func=run_eval)

    # show-results
    results_parser = subparsers.add_parser("show-results", help="Show experiment results log")
    results_parser.set_defaults(func=show_results)

    # iterate
    iterate_parser = subparsers.add_parser("iterate", help="Run auto-research improvement loop")
    iterate_parser.add_argument(
        "--sample-size",
        type=int,
        default=200,
        help="Sample size for manual iteration (default: 200)",
    )
    iterate_parser.add_argument(
        "--max-iterations",
        type=int,
        default=1,
        help="Proposals to test per manual run (default: 1)",
    )
    iterate_parser.add_argument(
        "--auto",
        action="store_true",
        help="Automatically test all remaining proposals until diminishing returns",
    )
    iterate_parser.add_argument(
        "--full",
        dest="sample_only",
        action="store_false",
        default=True,
        help="Use full 909 dataset instead of samples (auto mode always uses full)",
    )
    iterate_parser.set_defaults(func=iterate)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
