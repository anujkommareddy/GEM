# Project Context

## Current Objective

Make the research pipeline fully runnable locally with your own API keys (OpenAI first, Anthropic as alternative). No dependency on any hosted/remote Claude Code environment for the actual analysis runs.

## What Has Already Been Built

- **Full 6-stage research pipeline** in `research/`: ingest → labels → facets → analyze → hypothesis test → report
- **909 pilot scripts** ingested and linked to a master list of 1,102 shows (809 matched)
- **Provider abstraction** (`research/providers.py`) supporting both OpenAI and Anthropic with unified interface, retry logic, and cost tracking
- **Configurable CLI** (`research/cli.py`) with `--provider` and `--model` flags, `--mock` for dry runs
- **5-facet scoring framework** replacing the earlier 12-factor experiment
- **Statistical testing** with Cohen's d effect sizes, Welch's t-test, and stability analysis across 3 labeling schemes
- **Cached analysis results** — pipeline skips already-analyzed scripts on re-run
- **Pre-linked dataset** committed at `research/data/linked_dataset.json`

## What Was Learned From the Last Experiment

The initial run used 12 candidate factors with Anthropic's Claude (Haiku). Key takeaways:

1. **Too many factors created noise** — Some factors were redundant or poorly defined, making it hard to distinguish signal from noise in the statistical results.
2. **Grade inflation was a problem** — Early prompts allowed scores to cluster in 6-8 range, reducing discriminating power.
3. **The 5-facet framework is cleaner** — Consolidated to 5 well-defined facets with explicit scoring guidance, strong/weak signal definitions, and false positive warnings. Each facet is distinct and measurable from script text alone.
4. **Cost control matters** — Budget tracking and early termination were added after the first run exceeded expectations. The pipeline now defaults to the cheapest viable model per provider.
5. **Caching is essential** — Re-running the full 809-script batch is expensive. The pipeline now caches individual analyses and skips them on re-run.

## Current Direction

- **Returning to the 5-facet framework** as the basis for all future analysis
- **OpenAI local execution should be wired first** — it's the default provider, cheapest for batch runs (gpt-4o-mini at $0.15/$0.60 per million tokens), and doesn't require a hosted environment
- **Anthropic remains available** as an alternative provider for comparison or validation runs
- **Next step after local setup**: Run a small batch (e.g., 10-20 scripts with `--mock` first, then real) to verify the pipeline end-to-end before committing to a full 809-script run
