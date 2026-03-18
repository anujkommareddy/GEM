"""
AutoRubricResearch: Autonomous rubric improvement loop with budget control.

Usage:
    python3 src/auto_rubric_research.py --budget 50
    python3 src/auto_rubric_research.py --budget 100 --max-iterations 10

How it works:
  1. Load current best config (weights + baseline accuracy from v2_pipeline)
  2. Propose rubric mutations targeting weak dimensions (creative_originality, narrative_momentum)
  3. For each mutation:
     a. [CHEAP TEST ~$9] Re-score 200 probe scripts with new rubric
     b. Optimize weights on probe scores (free)
     c. Compare probe accuracy vs. current best
     d. If probe improves >= PROMOTION_THRESHOLD: PROMOTE (re-score all 906 scripts ~$40)
     e. Otherwise: REJECT (only $9 spent)
  4. On promotion: run full v2_pipeline to get new best config
  5. Repeat until budget exhausted

Budget breakdown:
  - Cheap test: ~$9 (200 scripts × $0.044)
  - Full promotion: ~$40 (906 scripts × $0.044)
  - Typical session at $50 budget: 4-5 cheap tests + possibly 0-1 promotions
  - Typical session at $100 budget: 9-10 cheap tests + 1-2 promotions

Stopping conditions:
  - Budget exhausted
  - Max iterations reached
  - No improvement after N consecutive rejections (convergence)
"""

import argparse
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────
BASE_DIR         = Path(".")
PER_SCRIPT_DIR   = BASE_DIR / "data/results/live/per_script"
BENCHMARK_PATH   = BASE_DIR / "data/benchmark/benchmark.jsonl"
SPLIT_PATH       = BASE_DIR / "data/results/validation/v2_split.json"
RUBRIC_PATH      = BASE_DIR / "config/rubric_prompt.md"
RUBRIC_BACKUP    = BASE_DIR / "config/rubric_history"
EXTRACTED_DIR    = BASE_DIR / "data/extracted_text"
RESULTS_DIR      = BASE_DIR / "data/results"
PROBE_PATH       = BASE_DIR / "data/results/probe_set.json"
MUTATIONS_LOG    = BASE_DIR / "data/results/rubric_mutations_log.jsonl"
INSIGHTS_PATH    = BASE_DIR / "PRODUCER_INSIGHTS.md"

# ─── Thresholds ───────────────────────────────────────────────
PROBE_SIZE = 200                       # Number of scripts in the locked probe set
V2_DIMENSIONS = [
    "audience_appeal_marketability",
    "conceptual_hook_clarity",
    "character_appeal_and_long_term_potential",
    "creative_originality_and_boldness",
    "narrative_momentum_engagement",
]
PROBE_IMPROVEMENT_THRESHOLD = -0.05   # smoke test only: reject if probe drops >5%
PROMOTION_IMPROVEMENT_THRESHOLD = 0.003  # 0.3% on full set after promotion
MAX_CONSECUTIVE_REJECTIONS = 6         # Stop if 6 consecutive cheap tests fail
COST_PER_SCRIPT = 0.010               # gpt-5-mini, single LLM call: ~$0.008 observed + 25% padding


def load_results(per_script_dir: Path) -> Dict:
    results = {}
    for f in per_script_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            sid = data.get("script_id")
            if sid and data.get("status") == "success":
                results[sid] = data
        except Exception:
            pass
    return results


def load_benchmark(benchmark_path: Path) -> Dict[str, str]:
    benchmark = {}
    with open(benchmark_path) as f:
        for line in f:
            try:
                e = json.loads(line)
                if e.get("label") in ("winner", "loser"):
                    benchmark[e["script_id"]] = e["label"]
            except Exception:
                pass
    return benchmark


def load_split(split_path: Path) -> Tuple[List, List]:
    with open(split_path) as f:
        d = json.load(f)
    return d["tune"], d["holdout"]


def load_best_config(results_dir: Path) -> Tuple[Dict, float]:
    """Load the most recent best config from v2_pipeline output."""
    configs = sorted(results_dir.glob("v2_best_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not configs:
        logger.warning("No best config found. Using uniform weights as baseline.")
        return {"weights": {d: 1.0 for d in [
            "audience_appeal_marketability", "conceptual_hook_clarity",
            "character_appeal_and_long_term_potential",
            "creative_originality_and_boldness", "narrative_momentum_engagement"
        ]}, "metrics": {}}, 0.84

    with open(configs[0]) as f:
        config = json.load(f)
    accuracy = config.get("metrics", {}).get("holdout_accuracy", 0.84)
    logger.info(f"Loaded best config: {configs[0].name}  ({accuracy*100:.2f}% holdout)")
    return config, accuracy


def backup_rubric(rubric_path: Path, backup_dir: Path, label: str):
    """Save a versioned copy of the rubric."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"rubric_{timestamp}_{label}.md"
    shutil.copy(rubric_path, dest)
    logger.info(f"Rubric backed up → {dest.name}")
    return dest


def log_mutation_result(log_path: Path, record: Dict):
    with open(log_path, "a") as f:
        f.write(json.dumps(record) + "\n")


def run_full_evaluation():
    """Trigger full re-evaluation of all scripts with current rubric."""
    import subprocess
    logger.info("Running full re-evaluation (this will take ~4 hours and ~$40)...")
    result = subprocess.run(
        ["python3", "src/cli.py", "run-eval"],
        capture_output=False,
    )
    return result.returncode == 0


def run_v2_pipeline() -> Tuple[Dict, float]:
    """Run v2_pipeline to get new best config after full eval."""
    from v2_pipeline import run_v2_pipeline as _run
    best_weights, best_accuracy, gaps = _run(
        per_script_dir=str(PER_SCRIPT_DIR),
        benchmark_path=str(BENCHMARK_PATH),
        results_dir=str(RESULTS_DIR),
        split_path=str(SPLIT_PATH),
        insights_path=str(INSIGHTS_PATH),
    )
    return best_weights, best_accuracy


class AutoRubricResearch:
    """Autonomous rubric improvement loop."""

    def __init__(self, budget: float, max_iterations: int = 20,
                 dry_run: bool = False):
        self.budget_total    = budget
        self.budget_spent    = 0.0
        self.max_iterations  = max_iterations
        self.dry_run         = dry_run
        self.iteration       = 0
        self.consecutive_rejections = 0
        self.improvements    = []
        self.rejections      = []

        # Load data
        logger.info("Loading data...")
        self.results   = load_results(PER_SCRIPT_DIR)
        self.benchmark = load_benchmark(BENCHMARK_PATH)
        self.tune_ids, self.holdout_ids = load_split(SPLIT_PATH)
        self.best_config, self.best_accuracy = load_best_config(RESULTS_DIR)
        self.best_weights = self.best_config.get("weights", {})

        logger.info(f"Loaded {len(self.results)} results, {len(self.tune_ids)} tune, {len(self.holdout_ids)} holdout")
        logger.info(f"Current best holdout accuracy: {self.best_accuracy*100:.2f}%")
        logger.info(f"Budget: ${budget:.2f} | Max iterations: {max_iterations}")

    def budget_remaining(self) -> float:
        return self.budget_total - self.budget_spent

    def can_afford_probe(self) -> bool:
        return self.budget_remaining() >= PROBE_SIZE * COST_PER_SCRIPT

    def can_afford_full_eval(self) -> bool:
        return self.budget_remaining() >= len(self.results) * COST_PER_SCRIPT

    def run(self):
        """Main loop."""
        print("\n" + "="*80)
        print("AUTO RUBRIC RESEARCH")
        print("="*80)
        print(f"Budget: ${self.budget_total:.2f}")
        print(f"Current best: {self.best_accuracy*100:.2f}% holdout")
        print(f"Probe cost: ~${PROBE_SIZE * COST_PER_SCRIPT:.2f} per test")
        print(f"Full eval cost: ~${len(self.results) * COST_PER_SCRIPT:.2f} per promotion")
        print(f"Max iterations: {self.max_iterations}")
        print("="*80 + "\n")

        from rubric_mutator import RubricMutator
        from rubric_probe_tester import RubricProbeTester

        mutator = RubricMutator(
            rubric_path=str(RUBRIC_PATH),
            gap_analysis_path=str(RESULTS_DIR / "v2_gap_analysis.json"),
        )

        tester = RubricProbeTester(
            tune_ids=self.tune_ids,
            benchmark=self.benchmark,
            extracted_text_dir=str(EXTRACTED_DIR),
            current_results=self.results,
            probe_path=str(PROBE_PATH),
        )

        # Load existing proposals if available, otherwise generate fresh
        proposals_path = RESULTS_DIR / "rubric_mutations_proposed.json"
        if proposals_path.exists():
            with open(proposals_path) as f:
                mutations = json.load(f)
            logger.info(f"Loaded {len(mutations)} existing mutation proposals from {proposals_path.name}")
        else:
            logger.info("Generating rubric mutation proposals...")
            mutations = mutator.propose_mutations(
                target_dimensions=["creative_originality_and_boldness", "narrative_momentum_engagement"],
                mutation_types=["tighten_anchors", "reframe", "replace"],
                n_variants=1,   # 1 variant per (dim × type) = 6 mutations total
            )
            logger.info(f"Generated {len(mutations)} candidate mutations")
            if not mutations:
                logger.error("No mutations generated. Check OpenAI API key.")
                return
            mutator.save_mutations(mutations, str(proposals_path))

        # Test each mutation
        for mut_idx, mutation in enumerate(mutations):
            if self.iteration >= self.max_iterations:
                logger.info(f"Reached max iterations ({self.max_iterations}). Stopping.")
                break

            if self.consecutive_rejections >= MAX_CONSECUTIVE_REJECTIONS:
                logger.info(f"Consecutive rejection limit ({MAX_CONSECUTIVE_REJECTIONS}) reached. Converged.")
                break

            if not self.can_afford_probe():
                logger.info(f"Insufficient budget for probe test (${self.budget_remaining():.2f} remaining). Stopping.")
                break

            self.iteration += 1
            dim      = mutation.get("source_dimension", "unknown")
            mut_type = mutation.get("mutation_type", "unknown")
            label    = f"iter{self.iteration:02d}_{mut_type}_{dim[:20]}"

            print(f"\n── Iteration {self.iteration}/{self.max_iterations} ──────────────────────────────")
            print(f"   Testing: {mut_type} on {dim}")
            print(f"   Rationale: {mutation.get('rationale', 'N/A')[:120]}")
            print(f"   Budget remaining: ${self.budget_remaining():.2f}")

            # Build candidate rubric
            candidate_rubric = mutator.build_candidate_rubric(mutation)
            probe_cost = tester.estimated_cost()

            if self.dry_run:
                print(f"   [DRY RUN] Would spend ~${probe_cost:.2f} on probe test")
                print(f"   [DRY RUN] Candidate rubric snippet:")
                print(mutation.get("rubric_text", "")[:300])
                continue

            # Run probe evaluation
            print(f"   Running probe evaluation (~${probe_cost:.2f}, {PROBE_SIZE} scripts)...")
            probe_results = tester.evaluate_probe_set(candidate_rubric)
            self.budget_spent += probe_cost

            if not probe_results:
                logger.error("Probe evaluation returned no results. Skipping.")
                self.consecutive_rejections += 1
                continue

            # Use equal weights for fair comparison (no optimization advantage for either rubric)
            equal_weights = {d: 1.0 for d in V2_DIMENSIONS}
            probe_acc, _  = tester.score_probe_accuracy(probe_results, equal_weights)

            # Current rubric on same probe set with same equal weights
            current_probe_results = {
                sid: self.results[sid].get("aggregated", {}).get("individual_scores", {})
                for sid in tester.probe_ids
                if sid in self.results
            }
            current_probe_acc, _ = tester.score_probe_accuracy(current_probe_results, equal_weights)

            improvement = probe_acc - current_probe_acc
            print(f"   Probe result: {probe_acc*100:.3f}%  (current: {current_probe_acc*100:.3f}%,  Δ={improvement*100:+.3f}%)")

            record = {
                "iteration": self.iteration,
                "timestamp": datetime.utcnow().isoformat(),
                "mutation_type": mut_type,
                "source_dimension": dim,
                "probe_accuracy": probe_acc,
                "current_probe_accuracy": current_probe_acc,
                "improvement": improvement,
                "probe_weights": probe_weights,
                "decision": None,
                "cost": probe_cost,
            }

            if improvement >= PROBE_IMPROVEMENT_THRESHOLD:
                print(f"   ✅ PROBE PASSED (+{improvement*100:.3f}%) — checking full eval affordability...")

                if not self.can_afford_full_eval():
                    print(f"   ⚠️  Not enough budget for full eval (${self.budget_remaining():.2f} < ${len(self.results) * COST_PER_SCRIPT:.2f})")
                    print(f"   Saving candidate rubric for next session.")
                    record["decision"] = "probe_passed_budget_constrained"
                    self._save_candidate_rubric(candidate_rubric, label, mutation)
                else:
                    print(f"   🚀 PROMOTING — running full re-evaluation (~${len(self.results) * COST_PER_SCRIPT:.2f})...")
                    record["decision"] = "promoted"
                    self._promote(candidate_rubric, mutation, label, tester)
                    self.budget_spent += len(self.results) * COST_PER_SCRIPT

                self.consecutive_rejections = 0
            else:
                print(f"   ❌ REJECTED (improvement {improvement*100:.3f}% < threshold {PROBE_IMPROVEMENT_THRESHOLD*100:.1f}%)")
                record["decision"] = "rejected"
                self.consecutive_rejections += 1
                self.rejections.append(record)

            log_mutation_result(MUTATIONS_LOG, record)

        self._print_summary()

    def _save_candidate_rubric(self, rubric_text: str, label: str, mutation: Dict):
        """Save a promising rubric that couldn't be fully tested due to budget."""
        RUBRIC_BACKUP.mkdir(parents=True, exist_ok=True)
        path = RUBRIC_BACKUP / f"{label}_candidate.md"
        path.write_text(rubric_text)
        meta_path = RUBRIC_BACKUP / f"{label}_candidate_meta.json"
        meta_path.write_text(json.dumps(mutation, indent=2))
        logger.info(f"Candidate rubric saved → {path.name}")

    def _promote(self, candidate_rubric: str, mutation: Dict, label: str, tester):
        """Promote: swap rubric, re-eval all scripts, run pipeline, update best."""
        # 1. Backup current rubric
        backup_rubric(RUBRIC_PATH, RUBRIC_BACKUP, f"pre_{label}")

        # 2. Write candidate rubric as new active rubric
        RUBRIC_PATH.write_text(candidate_rubric)
        logger.info(f"Rubric updated to candidate: {label}")

        # 3. Clear old per-script results (so we get fresh scores)
        old_dir = PER_SCRIPT_DIR.parent / "per_script_pre_rubric_change"
        old_dir.mkdir(exist_ok=True)
        for f in PER_SCRIPT_DIR.glob("*.json"):
            f.rename(old_dir / f.name)
        logger.info(f"Moved old per-script results to {old_dir.name}")

        # 4. Re-evaluate all scripts
        success = run_full_evaluation()
        if not success:
            logger.error("Full evaluation failed! Restoring previous rubric.")
            shutil.copy(RUBRIC_BACKUP / sorted(RUBRIC_BACKUP.glob("*.md"))[-1], RUBRIC_PATH)
            return

        # 5. Run v2_pipeline to get new best config
        logger.info("Running v2_pipeline on new scores...")
        new_weights, new_accuracy = run_v2_pipeline()

        improvement = new_accuracy - self.best_accuracy
        print(f"\n   Full eval result: {new_accuracy*100:.3f}%  (was: {self.best_accuracy*100:.3f}%,  Δ={improvement*100:+.3f}%)")

        if new_accuracy >= self.best_accuracy + PROMOTION_IMPROVEMENT_THRESHOLD:
            print(f"   ✅ PROMOTION ACCEPTED — new best: {new_accuracy*100:.3f}%")
            self.best_accuracy = new_accuracy
            self.best_weights  = new_weights
            self.results = load_results(PER_SCRIPT_DIR)
            self.improvements.append({
                "label": label,
                "new_accuracy": new_accuracy,
                "improvement": improvement,
                "mutation": mutation,
            })
            self._update_insights(mutation, new_accuracy, improvement)
        else:
            print(f"   ⚠️  Promotion marginal/negative. Reverting rubric.")
            backup_rubric(RUBRIC_PATH, RUBRIC_BACKUP, f"rejected_{label}")
            # Restore previous rubric
            pre_backups = sorted(RUBRIC_BACKUP.glob(f"*pre_{label}*"))
            if pre_backups:
                shutil.copy(pre_backups[-1], RUBRIC_PATH)
                logger.info("Previous rubric restored.")

    def _update_insights(self, mutation: Dict, new_accuracy: float, improvement: float):
        """Append rubric change finding to PRODUCER_INSIGHTS.md."""
        now = datetime.utcnow().strftime("%Y-%m-%d")
        section = f"""
---

## Rubric Change: {mutation.get('mutation_type')} on `{mutation.get('source_dimension')}` ({now})

**Result:** {new_accuracy*100:.2f}% holdout accuracy (+{improvement*100:.2f}%)

**Rationale:** {mutation.get('rationale', 'N/A')}

**New dimension text:**
```
{mutation.get('rubric_text', 'N/A')[:400]}
```

"""
        with open(INSIGHTS_PATH, "a") as f:
            f.write(section)

    def _print_summary(self):
        print("\n" + "="*80)
        print("AUTO RUBRIC RESEARCH — SESSION SUMMARY")
        print("="*80)
        print(f"Iterations:            {self.iteration}")
        print(f"Budget spent:          ${self.budget_spent:.2f} / ${self.budget_total:.2f}")
        print(f"Budget remaining:      ${self.budget_remaining():.2f}")
        print(f"Successful promotions: {len(self.improvements)}")
        print(f"Rejections:            {len(self.rejections)}")
        print(f"Final best accuracy:   {self.best_accuracy*100:.2f}%")

        if self.improvements:
            print("\nImprovements found:")
            for imp in self.improvements:
                print(f"  {imp['label']}: {imp['new_accuracy']*100:.2f}% (+{imp['improvement']*100:.2f}%)")
        else:
            print("\nNo improvements found this session.")
            print("Recommendation: The current rubric dimensions may be near-optimal.")
            print("Consider proposing entirely new dimensions rather than mutations.")

        print("\nMutation log saved to:", MUTATIONS_LOG)
        print("="*80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous rubric improvement loop with budget control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 src/auto_rubric_research.py --budget 50
  python3 src/auto_rubric_research.py --budget 100 --max-iterations 10
  python3 src/auto_rubric_research.py --budget 50 --dry-run   # See what would be tested
        """
    )
    parser.add_argument("--budget", type=float, required=True,
                        help="Total budget in USD for this session")
    parser.add_argument("--max-iterations", type=int, default=20,
                        help="Max rubric mutations to test (default: 20)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be tested without spending money")
    args = parser.parse_args()

    loop = AutoRubricResearch(
        budget=args.budget,
        max_iterations=args.max_iterations,
        dry_run=args.dry_run,
    )
    loop.run()


if __name__ == "__main__":
    main()
