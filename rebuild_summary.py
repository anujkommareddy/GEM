#!/usr/bin/env python3
"""Rebuild summary, leaderboard, and TSV from ALL per-script JSONs.

This reads every JSON in data/results/live/per_script/ and regenerates
the summary files, so the final output reflects ALL evaluated scripts
across all runs.
"""

import json
import csv
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

LIVE_DIR = Path("data/results/live")
PER_SCRIPT_DIR = LIVE_DIR / "per_script"
TSV_PATH = LIVE_DIR / "results_all.tsv"
LEADERBOARD_PATH = LIVE_DIR / "leaderboard.json"
SUMMARY_PATH = LIVE_DIR / "latest_summary.md"

TSV_FIELDS = [
    "timestamp", "script_id", "model", "status", "weighted_avg", "category",
    "singular_vision", "character_depth", "thematic_ambition",
    "emotional_specificity", "world_originality", "dialogue_language",
    "boldness", "label", "outcome", "error",
]

def load_all_results():
    """Load all per-script JSONs."""
    results = []
    for f in sorted(PER_SCRIPT_DIR.glob("*.json")):
        try:
            results.append(json.loads(f.read_text()))
        except Exception as e:
            print(f"  WARN: Could not read {f.name}: {e}")
    return results

def load_benchmark_labels():
    """Load outcome labels from benchmark."""
    labels = {}
    bench_file = Path("data/benchmark/benchmark.jsonl")
    if bench_file.exists():
        with open(bench_file) as f:
            for line in f:
                if line.strip():
                    d = json.loads(line)
                    labels[d["script_id"]] = {
                        "label": d.get("label"),
                        "outcome": d.get("outcome"),
                    }
    return labels

def dim_score(result, key):
    """Extract a dimension score from a result."""
    agg = result.get("aggregated", {})
    scores = agg.get("individual_scores", {})
    if key in scores:
        return scores[key]
    scoring = result.get("scoring", {})
    dim = scoring.get(key, {})
    if isinstance(dim, dict):
        return dim.get("score")
    return None

def write_tsv(results, labels):
    """Write complete TSV from all results."""
    with open(TSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=TSV_FIELDS, delimiter="\t")
        writer.writeheader()
        for r in results:
            sid = r.get("script_id", "")
            agg = r.get("aggregated", {})
            lab = labels.get(sid, {})
            writer.writerow({
                "timestamp": r.get("timestamp", ""),
                "script_id": sid,
                "model": r.get("model", ""),
                "status": r.get("status", ""),
                "weighted_avg": agg.get("weighted_average", ""),
                "category": agg.get("recommendation_category", ""),
                "singular_vision": dim_score(r, "singular_vision") or "",
                "character_depth": dim_score(r, "character_depth") or "",
                "thematic_ambition": dim_score(r, "thematic_ambition") or "",
                "emotional_specificity": dim_score(r, "emotional_specificity") or "",
                "world_originality": dim_score(r, "world_originality") or "",
                "dialogue_language": dim_score(r, "dialogue_language") or "",
                "boldness": dim_score(r, "boldness") or "",
                "label": lab.get("label", ""),
                "outcome": lab.get("outcome", ""),
                "error": r.get("error", ""),
            })
    print(f"Wrote {len(results)} rows to {TSV_PATH}")

def write_leaderboard(results):
    """Write leaderboard JSON."""
    scored = []
    for r in results:
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
        "total_scored": len(scored),
        "top_50": scored[:50],
        "bottom_10": scored[-10:] if len(scored) > 10 else [],
    }
    with open(LEADERBOARD_PATH, "w") as f:
        json.dump(leaderboard, f, indent=2)
    print(f"Wrote leaderboard ({len(scored)} scored scripts)")

def compute_pairwise_accuracy(results, labels):
    """Compute pairwise ranking accuracy: winners should score above losers."""
    score_map = {}
    for r in results:
        if r.get("status") == "success":
            agg = r.get("aggregated", {})
            wa = agg.get("weighted_average")
            if wa is not None:
                score_map[r["script_id"]] = wa

    winners = {sid for sid, lab in labels.items() if lab.get("outcome") == 1 and sid in score_map}
    losers = {sid for sid, lab in labels.items() if lab.get("outcome") == 0 and sid in score_map}

    correct = 0
    total = 0
    for w in winners:
        for l in losers:
            total += 1
            if score_map[w] > score_map[l]:
                correct += 1

    accuracy = correct / total if total > 0 else None
    return {
        "accuracy": accuracy,
        "correct_pairs": correct,
        "total_pairs": total,
        "winners_scored": len(winners),
        "losers_scored": len(losers),
        "winner_avg": sum(score_map[w] for w in winners) / len(winners) if winners else 0,
        "loser_avg": sum(score_map[l] for l in losers) / len(losers) if losers else 0,
    }

def compute_per_dimension_separation(results, labels):
    """For each dimension, compute average score for winners vs losers."""
    dims = ["singular_vision", "character_depth", "thematic_ambition",
            "emotional_specificity", "world_originality", "dialogue_language", "boldness"]

    winner_scores = defaultdict(list)
    loser_scores = defaultdict(list)

    for r in results:
        if r.get("status") != "success":
            continue
        sid = r["script_id"]
        lab = labels.get(sid, {})
        outcome = lab.get("outcome")
        if outcome is None:
            continue

        for dim in dims:
            s = dim_score(r, dim)
            if s is not None:
                if outcome == 1:
                    winner_scores[dim].append(s)
                else:
                    loser_scores[dim].append(s)

    separation = {}
    for dim in dims:
        w_avg = sum(winner_scores[dim]) / len(winner_scores[dim]) if winner_scores[dim] else 0
        l_avg = sum(loser_scores[dim]) / len(loser_scores[dim]) if loser_scores[dim] else 0
        separation[dim] = {
            "winner_avg": round(w_avg, 2),
            "loser_avg": round(l_avg, 2),
            "gap": round(w_avg - l_avg, 2),
            "winner_count": len(winner_scores[dim]),
            "loser_count": len(loser_scores[dim]),
        }

    return separation

def write_summary(results, labels):
    """Write comprehensive summary markdown."""
    total = len(results)
    successes = [r for r in results if r.get("status") == "success"]
    failures = [r for r in results if r.get("status") != "success"]

    # Scored scripts
    scored = []
    for r in successes:
        agg = r.get("aggregated", {})
        wa = agg.get("weighted_average")
        if wa is not None:
            scored.append((r["script_id"], wa, agg.get("recommendation_category", "")))
    scored.sort(key=lambda x: x[1], reverse=True)

    all_scores = [s[1] for s in scored]
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
    max_score = max(all_scores) if all_scores else 0
    min_score = min(all_scores) if all_scores else 0

    # Category distribution
    cat_dist = defaultdict(int)
    for _, _, cat in scored:
        cat_dist[cat] += 1

    # Pairwise accuracy
    pw = compute_pairwise_accuracy(results, labels)

    # Per-dimension separation
    dim_sep = compute_per_dimension_separation(results, labels)

    # Winners in the results
    winner_results = []
    for r in successes:
        sid = r["script_id"]
        lab = labels.get(sid, {})
        if lab.get("outcome") == 1:
            agg = r.get("aggregated", {})
            winner_results.append((sid, agg.get("weighted_average", 0), agg.get("recommendation_category", "")))
    winner_results.sort(key=lambda x: x[1], reverse=True)

    # False positives — losers scoring higher than lowest winner
    lowest_winner_score = min(w[1] for w in winner_results) if winner_results else 0
    false_positives = [(sid, sc, cat) for sid, sc, cat in scored
                       if labels.get(sid, {}).get("outcome") == 0 and sc >= lowest_winner_score]

    lines = [
        "# GEM Transcendence Detector — Full Results Summary",
        "",
        f"**Updated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
        f"**Model:** gpt-5-mini  ",
        f"**Total scripts in benchmark:** {len(labels)}  ",
        "",
        "---",
        "",
        "## Overall Stats",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Scripts evaluated | {total} |",
        f"| Successful | {len(successes)} |",
        f"| Failed | {len(failures)} |",
        f"| Mean score | {avg_score:.2f} |",
        f"| Max score | {max_score:.2f} |",
        f"| Min score | {min_score:.2f} |",
        "",
        "### Category Distribution",
        "",
        "| Category | Count |",
        "|---|---|",
    ]
    for cat in ["Transcendent", "Exceptional", "Promising", "Competent", "Generic"]:
        lines.append(f"| {cat} | {cat_dist.get(cat, 0)} |")

    lines += [
        "",
        "---",
        "",
        "## Pairwise Ranking Accuracy (THE KEY METRIC)",
        "",
        "Does the system score labeled winners above labeled losers?",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| **Pairwise accuracy** | **{pw['accuracy']*100:.1f}%** |" if pw['accuracy'] else "| Pairwise accuracy | N/A |",
        f"| Correct pairs | {pw['correct_pairs']:,} / {pw['total_pairs']:,} |",
        f"| Winners scored | {pw['winners_scored']} (of 73) |",
        f"| Losers scored | {pw['losers_scored']} (of 1029) |",
        f"| Winner avg score | {pw['winner_avg']:.2f} |",
        f"| Loser avg score | {pw['loser_avg']:.2f} |",
        f"| Score gap | {pw['winner_avg'] - pw['loser_avg']:.2f} |",
        "",
        "---",
        "",
        "## Per-Dimension Winner/Loser Separation",
        "",
        "Which dimensions best distinguish transcendent shows from the rest?",
        "",
        "| Dimension | Winner Avg | Loser Avg | Gap | Weight |",
        "|---|---|---|---|---|",
    ]

    weights = {
        "singular_vision": 0.25, "character_depth": 0.20, "thematic_ambition": 0.15,
        "emotional_specificity": 0.15, "world_originality": 0.10,
        "dialogue_language": 0.10, "boldness": 0.05,
    }
    dim_sorted = sorted(dim_sep.items(), key=lambda x: x[1]["gap"], reverse=True)
    for dim, data in dim_sorted:
        lines.append(f"| {dim.replace('_', ' ').title()} | {data['winner_avg']:.2f} | {data['loser_avg']:.2f} | **{data['gap']:+.2f}** | {weights.get(dim, 0):.0%} |")

    lines += [
        "",
        "---",
        "",
        "## Top 20 Scripts (Leaderboard)",
        "",
        "| Rank | Script | Score | Category | Label |",
        "|---|---|---|---|---|",
    ]
    for i, (sid, sc, cat) in enumerate(scored[:20], 1):
        lab = labels.get(sid, {})
        label_str = "WINNER" if lab.get("outcome") == 1 else "loser" if lab.get("outcome") == 0 else ""
        lines.append(f"| {i} | {sid} | {sc:.2f} | {cat} | {label_str} |")

    lines += [
        "",
        "---",
        "",
        f"## How Winners Scored ({len(winner_results)} evaluated)",
        "",
        "| Rank | Script | Score | Category |",
        "|---|---|---|---|",
    ]
    for i, (sid, sc, cat) in enumerate(winner_results, 1):
        lines.append(f"| {i} | {sid} | {sc:.2f} | {cat} |")

    lines += [
        "",
        "---",
        "",
        f"## False Positives ({len(false_positives)} losers scoring >= lowest winner)",
        "",
        f"Lowest winner score: {lowest_winner_score:.2f}",
        "",
        "| Script | Score | Category |",
        "|---|---|---|",
    ]
    for sid, sc, cat in false_positives[:30]:
        lines.append(f"| {sid} | {sc:.2f} | {cat} |")
    if len(false_positives) > 30:
        lines.append(f"| ... and {len(false_positives) - 30} more | | |")

    lines += ["", ""]

    with open(SUMMARY_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote summary to {SUMMARY_PATH}")


def main():
    print("Loading all per-script results...")
    results = load_all_results()
    print(f"  {len(results)} results loaded")

    print("Loading benchmark labels...")
    labels = load_benchmark_labels()
    print(f"  {len(labels)} labels loaded")

    print("\nRebuilding outputs...")
    write_tsv(results, labels)
    write_leaderboard(results)
    write_summary(results, labels)

    print("\nDone!")


if __name__ == "__main__":
    main()
