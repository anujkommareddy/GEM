"""
report_generator.py — GEM V1 Report / Explanation Layer

Generates a producer-facing report from existing v3 scoring outputs.
Pure read layer — does not re-score, does not modify any engine outputs.

Sources:
  - data/scoring/v3_expanded/per_script/{show_id}.json  → scores + reasoning
  - data/scoring/v3_expanded/best_weights.json           → weights + gap analysis
  - config/dimension_display.json                        → display names + descriptions
  - config/report_config.json                            → verdict thresholds + prompts

Usage:
  # Already-scored script (in corpus):
  python3 src/report_generator.py --show breaking-bad-101-pilot-2008

  # Fresh unseen script (score first, then report):
  python3 src/score_run.py --run v3_expanded --show-file my_script.txt
  python3 src/report_generator.py --show my_script_id

  # All flags:
  python3 src/report_generator.py --show SHOW_ID [--out path/to/report.json] [--no-llm] [--pretty]
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

# ─── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR       = Path(".")
V3_DIR         = BASE_DIR / "data/scoring/v3_expanded"
PER_SCRIPT_DIR = V3_DIR / "per_script"
WEIGHTS_FILE   = V3_DIR / "best_weights.json"
DISPLAY_FILE   = BASE_DIR / "config/dimension_display.json"
CONFIG_FILE    = BASE_DIR / "config/report_config.json"
REPORTS_DIR    = BASE_DIR / "data/reports"

ALL_DIMS = [
    "audience_appeal_marketability",
    "conceptual_hook_clarity",
    "character_appeal_and_long_term_potential",
    "creative_originality_and_boldness",
    "narrative_momentum_engagement",
    "resonant_originality",
    "world_density_and_texture",
    "tonal_specificity",
    "latent_depth_slow_burn_potential",
    "relationship_density_and_ensemble_engine",
]


# ─── Data Loading ───────────────────────────────────────────────────────────────

def load_score_record(show_id: str) -> dict:
    path = PER_SCRIPT_DIR / f"{show_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No score record found for '{show_id}'.\n"
            f"  Expected: {path}\n"
            f"  Run score_run.py first, or check the show_id spelling."
        )
    d = json.loads(path.read_text())
    if d.get("status") != "success":
        raise ValueError(f"Score record for '{show_id}' has status={d.get('status')}. Cannot generate report.")
    return d


def load_weights() -> dict:
    if not WEIGHTS_FILE.exists():
        raise FileNotFoundError(f"Weights file not found: {WEIGHTS_FILE}\nRun v3_optimizer.py first.")
    return json.loads(WEIGHTS_FILE.read_text())


def load_display() -> dict:
    return json.loads(DISPLAY_FILE.read_text())


def load_config() -> dict:
    return json.loads(CONFIG_FILE.read_text())


def load_all_scores_for_percentile() -> list:
    """Load weighted scores for all corpus scripts to compute percentile."""
    weights_data = load_weights()
    weights = weights_data["weights"]
    scores = []
    for f in PER_SCRIPT_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text())
            if d.get("status") != "success":
                continue
            scoring = d.get("scoring", {})
            ws = sum(
                scoring[dim]["score"] * weights.get(dim, 1.0)
                for dim in ALL_DIMS
                if dim in scoring and isinstance(scoring[dim], dict)
            )
            scores.append(ws)
        except Exception:
            pass
    return sorted(scores)


# ─── Scoring Computations ───────────────────────────────────────────────────────

def compute_weighted_score(scoring: dict, weights: dict) -> float:
    """Weighted sum of dimension scores, normalised to 0–100."""
    total_weight = sum(weights.get(d, 0) for d in ALL_DIMS)
    if total_weight == 0:
        return 0.0
    raw = sum(
        scoring[d]["score"] * weights.get(d, 0)
        for d in ALL_DIMS
        if d in scoring and isinstance(scoring[d], dict)
    )
    # Normalise: max possible raw = 10 × total_weight
    return round((raw / (10 * total_weight)) * 100, 1)


def compute_percentile(weighted_score_raw: float, corpus_scores: list) -> int:
    """Percentile rank of this script's raw weighted score against corpus."""
    if not corpus_scores:
        return 50
    below = sum(1 for s in corpus_scores if s < weighted_score_raw)
    return round(100 * below / len(corpus_scores))


def compute_raw_weighted(scoring: dict, weights: dict) -> float:
    """Raw (un-normalised) weighted sum — used for percentile comparison."""
    return sum(
        scoring[d]["score"] * weights.get(d, 0)
        for d in ALL_DIMS
        if d in scoring and isinstance(scoring[d], dict)
    )


def get_verdict(score_0_to_100: float, config: dict) -> tuple:
    thresholds = config["verdict_thresholds"]
    descriptions = config["verdict_descriptions"]
    for label, cutoff in sorted(thresholds.items(), key=lambda x: -x[1]):
        if score_0_to_100 >= cutoff:
            return label, descriptions[label]
    last = min(thresholds, key=thresholds.get)
    return last, descriptions[last]


def compute_strengths_and_risks(scoring: dict, weights: dict, config: dict, gap_analysis: dict = None):
    """
    Strengths: dimensions that are genuinely strong in absolute terms
               AND close to or above the winner benchmark.
               Avoids surfacing fake 'strengths' on uniformly weak scripts.

    Risks:     dimensions that are genuinely weak (below absolute floor)
               OR significantly below the winner benchmark.
    """
    if gap_analysis is None:
        gap_analysis = {}

    STRENGTH_FLOOR  = 6.5   # Must score at least this to be a real strength
    RISK_CEILING    = 5.5   # Anything at or below this is a genuine risk
    WINNER_GAP_RISK = -1.5  # >1.5 below winner avg is a risk regardless of abs score

    items = []
    for dim in ALL_DIMS:
        if dim not in scoring or not isinstance(scoring[dim], dict):
            continue
        score      = scoring[dim]["score"]
        w          = weights.get(dim, 0)
        winner_avg = gap_analysis.get(dim, {}).get("winner_avg", 6.0)
        vs_winner  = round(score - winner_avg, 2)
        items.append({
            "dimension":    dim,
            "score":        score,
            "weight":       w,
            "winner_avg":   winner_avg,
            "vs_winner":    vs_winner,
            "contribution": score * w,
        })

    n_s = config.get("n_strengths", 3)
    n_r = config.get("n_risks", 2)

    # Genuine strength: above absolute floor AND within 0.5 of winner avg (or above it)
    strengths = sorted(
        [i for i in items if i["score"] >= STRENGTH_FLOOR and i["vs_winner"] >= -0.5],
        key=lambda x: -x["contribution"]
    )[:n_s]

    # Genuine risk: below absolute ceiling OR significantly below winner avg
    # Sort by worst gap from winner first
    risks = sorted(
        [i for i in items if i["score"] <= RISK_CEILING or i["vs_winner"] <= WINNER_GAP_RISK],
        key=lambda x: x["vs_winner"]
    )[:n_r]

    return strengths, risks


# ─── Confidence ─────────────────────────────────────────────────────────────────

def compute_confidence(weighted_score: float, verdict_label: str) -> str:
    """
    How confident is the verdict?
    Based on distance from the nearest verdict boundary.
      HIGH   > 8 points from boundary
      MEDIUM  4–8 points
      LOW    < 4 points
    """
    if verdict_label == "STRONG SIGNAL":
        distance = weighted_score - 90
    elif verdict_label == "WORTH THE READ":
        distance = min(weighted_score - 72, 90 - weighted_score)
    elif verdict_label == "MIXED":
        distance = min(weighted_score - 50, 72 - weighted_score)
    else:  # PASS
        distance = 50 - weighted_score

    if distance >= 8:
        return "HIGH"
    elif distance >= 4:
        return "MEDIUM"
    else:
        return "LOW"


# ─── Read Recommendation ────────────────────────────────────────────────────────

def compute_read_recommendation(verdict_label: str, confidence: str) -> str:
    """Practical one-line read recommendation based on verdict + confidence."""
    if verdict_label == "STRONG SIGNAL":
        return "Prioritize for deeper read"
    elif verdict_label == "WORTH THE READ":
        if confidence == "HIGH":
            return "Worth reading this week"
        else:
            return "Worth a read — evaluate further"
    elif verdict_label == "MIXED":
        if confidence == "HIGH":
            return "Read only if slate has room"
        else:
            return "Not a priority read"
    else:  # PASS
        return "Pass in current form"


# ─── Opportunity Type ───────────────────────────────────────────────────────────

def compute_opportunity_type(scoring: dict, verdict_label: str) -> str:
    """
    Classify the type of creative/commercial opportunity this script represents.
    Based on the score profile of the highest-weight dimensions.
    """
    def s(dim):
        val = scoring.get(dim, {})
        return float(val.get("score", 0)) if isinstance(val, dict) else 0.0

    aa = s("audience_appeal_marketability")
    ts = s("tonal_specificity")
    ch = s("conceptual_hook_clarity")
    ca = s("character_appeal_and_long_term_potential")
    ro = s("resonant_originality")
    wd = s("world_density_and_texture")
    rd = s("relationship_density_and_ensemble_engine")

    if verdict_label == "STRONG SIGNAL":
        if aa >= 8.0 and ts >= 8.0:
            return "Commercial swing"
        elif ts >= 8.5:
            return "Voice-driven opportunity"
        elif aa >= 8.5:
            return "Market-ready, distinctive execution"
        elif ro >= 8.0:
            return "Prestige breakout potential"
        else:
            return "Strong all-around signal"

    elif verdict_label == "WORTH THE READ":
        if aa >= 7.5 and ts >= 7.0:
            return "Commercial swing with upside"
        elif ch >= 7.5 and ca < 6.5:
            return "Concept-led opportunity"
        elif ca >= 7.5 and rd >= 7.0:
            return "Character-led opportunity"
        elif ts >= 7.5:
            return "Voice-driven, needs development"
        elif ro >= 7.5:
            return "Prestige / niche potential"
        elif wd >= 7.5:
            return "World-led opportunity"
        else:
            return "Solid platform script"

    elif verdict_label == "MIXED":
        peak = max(
            s(d) for d in [
                "audience_appeal_marketability", "tonal_specificity",
                "world_density_and_texture", "resonant_originality",
                "conceptual_hook_clarity",
            ]
        )
        if peak >= 7.5:
            return "Strong sample, uneven execution"
        elif ch >= 6.5:
            return "Intriguing concept, underpowered script"
        else:
            return "Intriguing but underpowered"

    else:  # PASS
        return "Not yet competitive"


# ─── Highlights ─────────────────────────────────────────────────────────────────

def compute_highlights(
    strengths: list, risks: list,
    scoring: dict, display: dict, verdict_label: str
) -> dict:
    """
    For stronger scripts: 'Why It Stands Out' — bullets from genuine strengths.
    For mixed/pass scripts: 'What Would Need to Improve' — bullets from real risks.
    Grounded entirely in existing dimension reasoning. No LLM.
    """
    if verdict_label in ("STRONG SIGNAL", "WORTH THE READ"):
        highlight_type = "why_it_stands_out"
        source = strengths
    else:
        highlight_type = "what_would_need_to_improve"
        source = risks

    bullets = []
    for item in source[:3]:
        dim = item["dimension"]
        name = display.get(dim, {}).get("display_name", dim)
        dim_data = scoring.get(dim, {})
        reasoning = dim_data.get("reasoning", "") if isinstance(dim_data, dict) else ""
        if reasoning:
            bullets.append(f"{name}: {reasoning}")

    if not bullets:
        if highlight_type == "why_it_stands_out":
            bullets = ["No dimensions scored above the winner benchmark in current form."]
        else:
            bullets = ["Most dimensions are performing near or above the winner benchmark."]

    return {"type": highlight_type, "bullets": bullets}


# ─── One-Line LLM Synthesis ────────────────────────────────────────────────────

def generate_one_line(scoring: dict, weights: dict, config: dict) -> str:
    """
    Single tightly-constrained LLM call.
    Uses only the top-weighted dimensions' existing reasoning — no new claims.
    Falls back to a template string if no API key is available.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return _fallback_one_line(scoring, weights)

    # Select top 3 weighted dims with the highest scores for grounding
    ranked = sorted(
        [d for d in ALL_DIMS if d in scoring and isinstance(scoring[d], dict)],
        key=lambda d: scoring[d]["score"] * weights.get(d, 0),
        reverse=True,
    )
    top_dims = ranked[:3]

    reasoning_block = "\n".join(
        f"- {dim}: {scoring[dim]['reasoning']}"
        for dim in top_dims
    )

    prompt_template = config.get("one_line_prompt", "")
    prompt = prompt_template.format(reasoning_block=reasoning_block)

    try:
        import openai
        client = openai.OpenAI(api_key=api_key, timeout=30.0, max_retries=1)
        resp = client.chat.completions.create(
            model=config.get("one_line_model", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=60,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip().strip('"')
    except Exception:
        return _fallback_one_line(scoring, weights)


def _fallback_one_line(scoring: dict, weights: dict) -> str:
    """No-LLM fallback: grab the strongest dimension's reasoning, first sentence."""
    best_dim = max(
        [d for d in ALL_DIMS if d in scoring and isinstance(scoring[d], dict)],
        key=lambda d: scoring[d]["score"] * weights.get(d, 0),
    )
    reasoning = scoring[best_dim]["reasoning"]
    first_sentence = reasoning.split(".")[0].strip()
    return first_sentence + "."


# ─── Producer Takeaway ─────────────────────────────────────────────────────────

def generate_producer_takeaway(verdict_label: str, percentile: int,
                                strengths: list, risks: list,
                                display: dict,
                                read_recommendation: str = "",
                                opportunity_type: str = "") -> str:
    """
    Actionable decision memo. Template-based, no LLM.
    Answers: what should I do, what kind of opportunity is this, why.
    """
    parts = []

    if read_recommendation:
        parts.append(f"{read_recommendation}.")

    if strengths:
        top_name = display.get(strengths[0]["dimension"], {}).get("display_name", strengths[0]["dimension"])
        parts.append(f"Lead signal: {top_name}.")

    if risks:
        top_risk = display.get(risks[0]["dimension"], {}).get("display_name", risks[0]["dimension"])
        parts.append(f"Watch: {top_risk}.")

    parts.append(f"Outscores {percentile}% of the GEM corpus.")

    return " ".join(parts)


# ─── Report Assembly ────────────────────────────────────────────────────────────

def build_report(show_id: str, use_llm: bool = True) -> dict:
    record       = load_score_record(show_id)
    weights_data = load_weights()
    weights      = weights_data["weights"]
    gap_analysis = weights_data.get("gap_analysis", {})
    display      = load_display()
    config       = load_config()
    scoring      = record["scoring"]

    # ── Core scores ───────────────────────────────────────────────────────────
    raw_weighted   = compute_raw_weighted(scoring, weights)
    corpus_scores  = load_all_scores_for_percentile()
    percentile     = compute_percentile(raw_weighted, corpus_scores)
    weighted_score = compute_weighted_score(scoring, weights)
    verdict_label, verdict_desc = get_verdict(weighted_score, config)

    # ── Strengths / Risks (benchmark-aware) ──────────────────────────────────
    strengths, risks = compute_strengths_and_risks(scoring, weights, config, gap_analysis)

    # ── Decision layer ────────────────────────────────────────────────────────
    confidence          = compute_confidence(weighted_score, verdict_label)
    read_recommendation = compute_read_recommendation(verdict_label, confidence)
    opportunity_type    = compute_opportunity_type(scoring, verdict_label)
    highlights          = compute_highlights(strengths, risks, scoring, display, verdict_label)

    # ── One-line summary ──────────────────────────────────────────────────────
    if use_llm:
        one_line = generate_one_line(scoring, weights, config)
    else:
        one_line = _fallback_one_line(scoring, weights)

    # ── Dimension breakdown ───────────────────────────────────────────────────
    dim_breakdown = []
    for dim in ALL_DIMS:
        if dim not in scoring or not isinstance(scoring[dim], dict):
            continue
        score     = scoring[dim]["score"]
        reasoning = scoring[dim]["reasoning"]
        info      = display.get(dim, {})
        gap_data  = gap_analysis.get(dim, {})
        dim_breakdown.append({
            "dimension":       dim,
            "display_name":    info.get("display_name", dim),
            "short_desc":      info.get("short_desc", ""),
            "score":           score,
            "weight":          weights.get(dim, 0),
            "winner_avg":      round(gap_data.get("winner_avg", 0), 1),
            "vs_winner_avg":   round(score - gap_data.get("winner_avg", score), 1),
            "reasoning":       reasoning,
        })

    # Sort by weighted contribution (highest first) for display
    dim_breakdown.sort(key=lambda x: -(x["score"] * x["weight"]))

    # ── Producer takeaway ─────────────────────────────────────────────────────
    producer_takeaway = generate_producer_takeaway(
        verdict_label, percentile, strengths, risks, display,
        read_recommendation, opportunity_type
    )

    return {
        "show_id":        show_id,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "engine_version": record.get("run_id", "v3_expanded"),
        "model":          record.get("model", "gpt-4o-mini"),
        "scoring_mode":   record.get("scoring_mode", ""),

        "verdict": {
            "label":          verdict_label,
            "weighted_score": weighted_score,
            "percentile":     percentile,
            "description":    verdict_desc,
            "one_line":       one_line,
        },

        "confidence":          confidence,
        "read_recommendation": read_recommendation,
        "opportunity_type":    opportunity_type,
        "highlights":          highlights,

        "strengths": [
            {
                "dimension":    s["dimension"],
                "display_name": display.get(s["dimension"], {}).get("display_name", s["dimension"]),
                "score":        s["score"],
                "note":         scoring[s["dimension"]]["reasoning"],
            }
            for s in strengths
        ],

        "risks": [
            {
                "dimension":    r["dimension"],
                "display_name": display.get(r["dimension"], {}).get("display_name", r["dimension"]),
                "score":        r["score"],
                "note":         scoring[r["dimension"]]["reasoning"],
            }
            for r in risks
        ],

        "dimensions": dim_breakdown,

        "producer_takeaway": producer_takeaway,
    }


# ─── Pretty Print ───────────────────────────────────────────────────────────────

def print_report(report: dict):
    v = report["verdict"]
    print(f"\n{'='*70}")
    print(f"  GEM SCRIPT REPORT")
    print(f"{'='*70}")
    print(f"  Script:    {report['show_id']}")
    print(f"  Engine:    {report['engine_version']}  ({report['model']})")
    print(f"{'='*70}")
    print(f"\n  VERDICT:   {v['label']}")
    pct = v['percentile']
    if pct >= 90:
        pct_str = f"top {100 - pct}% of corpus"
    elif pct <= 10:
        pct_str = f"bottom {pct + 1}% of corpus"
    else:
        pct_str = f"{pct}th percentile of corpus"
    print(f"  Score:     {v['weighted_score']}/100  ({pct_str})")
    print(f"\n  \"{v['one_line']}\"")
    print(f"\n  {v['description']}")

    if report["strengths"]:
        print(f"\n{'─'*70}")
        print(f"  WHAT'S WORKING")
        print(f"{'─'*70}")
        for s in report["strengths"]:
            print(f"\n  [{s['score']}/10] {s['display_name']}")
            print(f"  {s['note']}")

    if report["risks"]:
        print(f"\n{'─'*70}")
        print(f"  WHAT MAY HOLD IT BACK")
        print(f"{'─'*70}")
        for r in report["risks"]:
            print(f"\n  [{r['score']}/10] {r['display_name']}")
            print(f"  {r['note']}")

    print(f"\n{'─'*70}")
    print(f"  DIMENSION BREAKDOWN")
    print(f"{'─'*70}")
    print(f"  {'Dimension':<42} {'Score':>6}  {'vs Winners':>11}")
    print(f"  {'-'*62}")
    for d in report["dimensions"]:
        vs = d["vs_winner_avg"]
        vs_str = f"{vs:+.1f}" if vs != 0 else "  —"
        print(f"  {d['display_name']:<42} {d['score']:>5}/10  {vs_str:>10}")

    print(f"\n{'─'*70}")
    print(f"  PRODUCER TAKEAWAY")
    print(f"{'─'*70}")
    print(f"  {report['producer_takeaway']}")
    print(f"\n{'='*70}\n")


# ─── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="GEM Report Generator")
    parser.add_argument("--show",   required=True,
                        help="Show ID (must have an existing score record in v3_expanded/per_script/)")
    parser.add_argument("--out",    default=None,
                        help="Output path for JSON report (default: data/reports/{show_id}.json)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip the one-line LLM synthesis call (uses fallback template)")
    parser.add_argument("--pretty", action="store_true", default=True,
                        help="Print formatted report to stdout (default: True)")
    parser.add_argument("--json-only", action="store_true",
                        help="Only write JSON, suppress stdout report")
    args = parser.parse_args()

    try:
        report = build_report(args.show, use_llm=not args.no_llm)
    except (FileNotFoundError, ValueError) as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Write JSON
    out_path = Path(args.out) if args.out else REPORTS_DIR / f"{args.show}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2))

    if not args.json_only:
        print_report(report)

    print(f"Report saved → {out_path}")


if __name__ == "__main__":
    main()
