"""Live output writer for continuous, readable intermediate results.

Outputs are written to data/live/ with this structure:
    data/live/
        results.tsv              <- one row appended per script eval, immediately
        leaderboard.json         <- top scripts, refreshed after every eval
        latest_summary.md        <- human-readable dashboard, refreshed periodically
        per_script/              <- one JSON per script with full eval details
            <script_id>.json
"""

import csv
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# How often to rewrite the summary file (seconds)
SUMMARY_REFRESH_INTERVAL = 30
LEADERBOARD_SIZE = 50


class LiveOutputWriter:
    """Writes evaluation results to disk continuously during a run."""

    def __init__(self, output_dir: str | Path, model: str, run_id: str = None):
        self.output_dir = Path(output_dir)
        self.model = model
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Directories
        self.live_dir = self.output_dir / "live"
        self.per_script_dir = self.live_dir / "per_script"
        self.live_dir.mkdir(parents=True, exist_ok=True)
        self.per_script_dir.mkdir(parents=True, exist_ok=True)

        # File paths
        self.tsv_path = self.live_dir / "results.tsv"
        self.leaderboard_path = self.live_dir / "leaderboard.json"
        self.summary_path = self.live_dir / "latest_summary.md"
        self.run_meta_path = self.live_dir / "run_meta.json"

        # In-memory state
        self._results: List[Dict] = []
        self._start_time = time.time()
        self._last_summary_write = 0.0
        self._total_scripts = 0
        self._total_tokens_estimate = 0

        # Initialize TSV with headers
        self._init_tsv()

        # Write initial run metadata
        self._write_run_meta("running")

        logger.info(f"Live output directory: {self.live_dir}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_total_scripts(self, n: int):
        """Tell the writer how many scripts will be evaluated."""
        self._total_scripts = n

    def record_result(self, result: Dict, entry=None):
        """Record one script evaluation result. Writes immediately to disk."""
        self._results.append(result)

        # 1. Append to TSV immediately
        self._append_tsv_row(result, entry)

        # 2. Write per-script JSON
        self._write_per_script_json(result)

        # 3. Update leaderboard (every result)
        self._write_leaderboard()

        # 4. Update summary on interval
        now = time.time()
        if now - self._last_summary_write >= SUMMARY_REFRESH_INTERVAL:
            self._write_summary()
            self._last_summary_write = now

    def finalize(self):
        """Write final versions of all output files."""
        self._write_leaderboard()
        self._write_summary()
        self._write_run_meta("completed")
        logger.info(f"Final live outputs written to {self.live_dir}")

    # ------------------------------------------------------------------
    # TSV
    # ------------------------------------------------------------------

    _TSV_FIELDS = [
        "timestamp",
        "script_id",
        "model",
        "status",
        "weighted_avg",
        "category",
        "singular_vision",
        "character_depth",
        "thematic_ambition",
        "emotional_specificity",
        "world_originality",
        "dialogue_language",
        "boldness",
        "label",
        "outcome",
        "error",
    ]

    def _init_tsv(self):
        """Create TSV with header row if it doesn't exist yet."""
        if not self.tsv_path.exists():
            with open(self.tsv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self._TSV_FIELDS, delimiter="\t")
                writer.writeheader()
                f.flush()
                os.fsync(f.fileno())

    def _append_tsv_row(self, result: Dict, entry=None):
        """Append one row and flush."""
        agg = result.get("aggregated", {})
        scores = agg.get("individual_scores", {})
        scoring = result.get("scoring", {})

        def _dim_score(key):
            """Pull score from aggregated individual_scores or from scoring dict."""
            if key in scores:
                return scores[key]
            dim = scoring.get(key, {})
            if isinstance(dim, dict):
                return dim.get("score")
            return None

        row = {
            "timestamp": result.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "script_id": result.get("script_id", ""),
            "model": result.get("model", self.model),
            "status": result.get("status", ""),
            "weighted_avg": agg.get("weighted_average", ""),
            "category": agg.get("recommendation_category", ""),
            "singular_vision": _dim_score("singular_vision") or "",
            "character_depth": _dim_score("character_depth") or "",
            "thematic_ambition": _dim_score("thematic_ambition") or "",
            "emotional_specificity": _dim_score("emotional_specificity") or "",
            "world_originality": _dim_score("world_originality") or "",
            "dialogue_language": _dim_score("dialogue_language") or "",
            "boldness": _dim_score("boldness") or "",
            "label": getattr(entry, "label", "") if entry else "",
            "outcome": getattr(entry, "outcome", "") if entry else "",
            "error": result.get("error", ""),
        }

        with open(self.tsv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self._TSV_FIELDS, delimiter="\t")
            writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())

    # ------------------------------------------------------------------
    # Per-script JSON
    # ------------------------------------------------------------------

    def _write_per_script_json(self, result: Dict):
        """Write one JSON file per script."""
        script_id = result.get("script_id", "unknown")
        safe_name = script_id.replace("/", "_").replace("\\", "_")
        path = self.per_script_dir / f"{safe_name}.json"
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

    # ------------------------------------------------------------------
    # Leaderboard
    # ------------------------------------------------------------------

    def _write_leaderboard(self):
        """Write top-N scripts ranked by weighted average."""
        scored = []
        for r in self._results:
            if r.get("status") != "success":
                continue
            agg = r.get("aggregated", {})
            wa = agg.get("weighted_average")
            if wa is not None:
                scored.append({
                    "script_id": r["script_id"],
                    "weighted_avg": wa,
                    "category": agg.get("recommendation_category", ""),
                    "individual_scores": agg.get("individual_scores", {}),
                })

        scored.sort(key=lambda x: x["weighted_avg"], reverse=True)

        leaderboard = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "model": self.model,
            "scripts_scored": len(scored),
            "top": scored[:LEADERBOARD_SIZE],
            "bottom": scored[-10:] if len(scored) > 10 else [],
        }

        with open(self.leaderboard_path, "w") as f:
            json.dump(leaderboard, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

    # ------------------------------------------------------------------
    # Summary markdown
    # ------------------------------------------------------------------

    def _write_summary(self):
        """Write a human-readable summary markdown file."""
        elapsed = time.time() - self._start_time
        total = len(self._results)
        successes = [r for r in self._results if r.get("status") == "success"]
        failures = [r for r in self._results if r.get("status") != "success"]

        # Best scripts
        scored = []
        for r in successes:
            agg = r.get("aggregated", {})
            wa = agg.get("weighted_average")
            if wa is not None:
                scored.append((r["script_id"], wa, agg.get("recommendation_category", "")))
        scored.sort(key=lambda x: x[1], reverse=True)

        # Category distribution
        cat_dist: Dict[str, int] = {}
        for _, _, cat in scored:
            cat_dist[cat] = cat_dist.get(cat, 0) + 1

        # Score stats
        all_scores = [s[1] for s in scored]
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        max_score = max(all_scores) if all_scores else 0
        min_score = min(all_scores) if all_scores else 0

        # Estimate cost: ~12k tokens per script (extraction) + ~10k tokens (scoring)
        # GPT-5-mini pricing estimate: ~$0.002 per 1k tokens
        est_tokens = total * 22_000
        est_cost = est_tokens * 0.000002  # rough

        # Error types
        error_types: Dict[str, int] = {}
        for r in failures:
            err = r.get("error", "unknown")[:80]
            error_types[err] = error_types.get(err, 0) + 1

        # Progress
        pct = (total / self._total_scripts * 100) if self._total_scripts else 0
        rate = total / elapsed * 60 if elapsed > 0 else 0  # scripts per minute
        eta_min = (self._total_scripts - total) / (rate if rate > 0 else 1)

        lines = [
            f"# GEM Autoresearch — Live Run Summary",
            f"",
            f"**Run ID:** `{self.run_id}`  ",
            f"**Model:** `{self.model}`  ",
            f"**Updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
            f"",
            f"---",
            f"",
            f"## Progress",
            f"",
            f"| Metric | Value |",
            f"|---|---|",
            f"| Scripts evaluated | {total} / {self._total_scripts} ({pct:.1f}%) |",
            f"| Successful | {len(successes)} |",
            f"| Failed | {len(failures)} |",
            f"| Elapsed | {elapsed/60:.1f} min |",
            f"| Rate | {rate:.1f} scripts/min |",
            f"| ETA | {eta_min:.0f} min remaining |",
            f"| Est. tokens used | ~{est_tokens:,} |",
            f"| Est. cost | ~${est_cost:.2f} |",
            f"",
            f"---",
            f"",
            f"## Best Current Scripts (Top 10)",
            f"",
            f"| Rank | Script | Score | Category |",
            f"|---|---|---|---|",
        ]
        for i, (sid, sc, cat) in enumerate(scored[:10], 1):
            lines.append(f"| {i} | {sid} | {sc:.2f} | {cat} |")

        lines += [
            f"",
            f"---",
            f"",
            f"## Score Distribution",
            f"",
            f"| Stat | Value |",
            f"|---|---|",
            f"| Mean | {avg_score:.2f} |",
            f"| Max | {max_score:.2f} |",
            f"| Min | {min_score:.2f} |",
            f"",
            f"### By Category",
            f"",
            f"| Category | Count |",
            f"|---|---|",
        ]
        for cat in ["Transcendent", "Exceptional", "Promising", "Competent", "Generic"]:
            lines.append(f"| {cat} | {cat_dist.get(cat, 0)} |")

        if error_types:
            lines += [
                f"",
                f"---",
                f"",
                f"## Errors ({len(failures)} total)",
                f"",
                f"| Error | Count |",
                f"|---|---|",
            ]
            for err, cnt in sorted(error_types.items(), key=lambda x: -x[1]):
                lines.append(f"| `{err}` | {cnt} |")

        # Recommended next moves
        lines += [
            f"",
            f"---",
            f"",
            f"## Recommended Next Moves",
            f"",
        ]
        if len(successes) == 0:
            lines.append("- Check API key and model configuration — no successful evaluations yet.")
        else:
            if len(failures) > len(successes) * 0.1:
                lines.append(f"- High failure rate ({len(failures)}/{total}). Investigate error patterns above.")
            if avg_score > 7:
                lines.append("- Scores running high — consider tightening the rubric to improve discrimination.")
            elif avg_score < 4:
                lines.append("- Scores running low — review rubric for excessive strictness.")
            transcendent = cat_dist.get("Transcendent", 0) + cat_dist.get("Exceptional", 0)
            if transcendent > 0:
                lines.append(f"- {transcendent} scripts rated Exceptional or Transcendent — review these against known winners.")
            if total >= 50 and len(scored) >= 50:
                lines.append("- 50+ scripts scored — enough data to compute pairwise ranking accuracy against benchmark labels.")
            if total < self._total_scripts:
                lines.append(f"- Run still in progress. {self._total_scripts - total} scripts remaining.")

        lines.append("")

        md = "\n".join(lines)
        with open(self.summary_path, "w") as f:
            f.write(md)
            f.flush()
            os.fsync(f.fileno())

    # ------------------------------------------------------------------
    # Run metadata
    # ------------------------------------------------------------------

    def _write_run_meta(self, status: str):
        meta = {
            "run_id": self.run_id,
            "model": self.model,
            "status": status,
            "started_at": datetime.fromtimestamp(self._start_time, tz=timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_scripts": self._total_scripts,
            "evaluated": len(self._results),
            "successful": len([r for r in self._results if r.get("status") == "success"]),
            "failed": len([r for r in self._results if r.get("status") != "success"]),
            "output_dir": str(self.live_dir),
            "files": {
                "tsv": str(self.tsv_path),
                "leaderboard": str(self.leaderboard_path),
                "summary": str(self.summary_path),
                "per_script": str(self.per_script_dir),
            },
        }
        with open(self.run_meta_path, "w") as f:
            json.dump(meta, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
