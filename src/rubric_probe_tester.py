"""
RubricProbeTester: Tests a candidate rubric on a small locked probe set.

Design:
  - Uses a LOCKED 200-script probe set sampled from the TUNE set (not holdout)
  - Re-evaluates those scripts with the candidate rubric via single LLM call
  - Runs quick weight optimization (free) on the probe scores
  - Returns pairwise accuracy on probe set
  - Cost: ~200 × $0.044 = ~$8.80 per test

Gating logic (in auto_rubric_research.py):
  - If probe accuracy improves ≥ PROMOTION_THRESHOLD over current best → promote to full eval
  - Otherwise → reject (only $8.80 spent)
"""

import json
import os
import random
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

PROBE_SIZE = 200
PROBE_SEED = 17   # Locked forever — never change this
COST_PER_SCRIPT = 0.010  # gpt-5-mini, single LLM call: ~$0.008 observed + 25% padding

V2_DIMENSIONS = [
    "audience_appeal_marketability",
    "conceptual_hook_clarity",
    "character_appeal_and_long_term_potential",
    "creative_originality_and_boldness",
    "narrative_momentum_engagement",
]


class RubricProbeTester:
    """Tests candidate rubrics on a locked probe set."""

    def __init__(self,
                 tune_ids: List[str],
                 benchmark: Dict[str, str],
                 extracted_text_dir: str,
                 current_results: Dict,
                 probe_path: str = "./data/results/probe_set.json"):
        self.tune_ids = tune_ids
        self.benchmark = benchmark
        self.text_dir = Path(extracted_text_dir)
        self.current_results = current_results
        self.probe_path = Path(probe_path)

        import openai
        self.client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

        # Load or create the locked probe set
        self.probe_ids = self._load_or_create_probe_set()

    def _load_or_create_probe_set(self) -> List[str]:
        """Create or load the locked probe set (sampled from tune, stratified)."""
        if self.probe_path.exists():
            with open(self.probe_path) as f:
                data = json.load(f)
            logger.info(f"Loaded existing probe set: {len(data['probe_ids'])} scripts")
            return data["probe_ids"]

        # Create new probe set: stratified sample from tune
        rng = random.Random(PROBE_SEED)
        tune_winners = [s for s in self.tune_ids if self.benchmark.get(s) == "winner"]
        tune_losers  = [s for s in self.tune_ids if self.benchmark.get(s) == "loser"]

        # Aim for ~probe_size scripts with same winner ratio as tune set
        winner_ratio = len(tune_winners) / len(self.tune_ids) if self.tune_ids else 0.08
        n_winners = max(5, min(len(tune_winners), int(PROBE_SIZE * winner_ratio)))
        n_losers  = min(len(tune_losers), PROBE_SIZE - n_winners)

        probe_winners = rng.sample(tune_winners, n_winners)
        probe_losers  = rng.sample(tune_losers,  n_losers)
        probe_ids     = probe_winners + probe_losers

        self.probe_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.probe_path, "w") as f:
            json.dump({
                "probe_ids": probe_ids,
                "n_winners": n_winners,
                "n_losers": n_losers,
                "seed": PROBE_SEED,
                "created_at": datetime.utcnow().isoformat(),
            }, f, indent=2)

        logger.info(f"Created probe set: {len(probe_ids)} scripts ({n_winners} winners, {n_losers} losers)")
        return probe_ids

    def _load_script_text(self, script_id: str) -> Optional[str]:
        """Load extracted text for a script."""
        txt_file = self.text_dir / f"{script_id}.txt"
        if txt_file.exists():
            return txt_file.read_text(encoding="utf-8", errors="ignore")[:15000]
        return None

    def evaluate_probe_set(self, candidate_rubric: str, dimension_names: List[str] = None) -> Dict:
        """
        Re-evaluate the probe set with a candidate rubric.

        Args:
            candidate_rubric: Full rubric text for the candidate
            dimension_names: List of dimension names in the rubric (defaults to V2_DIMENSIONS)

        Returns:
            Dict of {script_id: {dim: score}} for all probe scripts
        """
        if dimension_names is None:
            dimension_names = V2_DIMENSIONS

        results = {}
        n_probe = len(self.probe_ids)
        failed = 0

        for i, script_id in enumerate(self.probe_ids, 1):
            script_text = self._load_script_text(script_id)
            if not script_text:
                logger.warning(f"[{i}/{n_probe}] {script_id} — no text found, skipping")
                failed += 1
                continue

            try:
                scores = self._score_script(script_id, script_text, candidate_rubric)
                results[script_id] = scores
                if i % 25 == 0:
                    logger.info(f"  [{i}/{n_probe}] Probe eval progress... ({failed} failed)")
            except Exception as e:
                logger.error(f"[{i}/{n_probe}] {script_id} failed: {e}")
                failed += 1

        logger.info(f"Probe evaluation complete: {len(results)}/{n_probe} succeeded ({failed} failed)")
        return results

    def _score_script(self, script_id: str, script_text: str, rubric: str) -> Dict:
        """Single-pass LLM scoring with candidate rubric."""
        prompt = f"""{rubric}

---

## Script to Evaluate

**Script ID:** {script_id}

**Full Script Text:**

{script_text}

---

## Your Evaluation

Please provide a JSON evaluation. Score each dimension 1-10 with reasoning.

IMPORTANT: Always use these exact JSON keys regardless of how dimensions are named in the rubric above:
- audience_appeal_marketability
- conceptual_hook_clarity
- character_appeal_and_long_term_potential
- creative_originality_and_boldness
- narrative_momentum_engagement

Return ONLY valid JSON, no other text."""

        response = self.client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=2000,
        )
        raw = response.choices[0].message.content.strip()

        if not raw:
            raise ValueError(f"Empty response from model for {script_id}")

        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()

        # Find the JSON object if there's surrounding text
        if not raw.startswith("{"):
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start != -1 and end > start:
                raw = raw[start:end]
            else:
                raise ValueError(f"No JSON object found in response for {script_id}. Raw: {raw[:200]}")

        parsed = json.loads(raw)
        # Extract just the scores
        scores = {}
        for dim in V2_DIMENSIONS:
            val = parsed.get(dim, {})
            if isinstance(val, dict):
                scores[dim] = val.get("score", 0)
            elif isinstance(val, (int, float)):
                scores[dim] = float(val)

        # Also handle replacement dimensions (new name might be in the parsed output)
        for key, val in parsed.items():
            if key not in scores and key not in ("summary", "overall"):
                if isinstance(val, dict) and "score" in val:
                    scores[key] = val["score"]
                elif isinstance(val, (int, float)):
                    scores[key] = float(val)

        return scores

    def score_probe_accuracy(self, probe_results: Dict,
                              weights: Dict[str, float] = None) -> Tuple[float, float]:
        """
        Compute pairwise accuracy + top-10% enrichment on probe set.

        Args:
            probe_results: {script_id: {dim: score}}
            weights: dimension weights (default: equal)

        Returns:
            (pairwise_accuracy, top10_enrichment)
        """
        if weights is None:
            dims = list(next(iter(probe_results.values())).keys()) if probe_results else V2_DIMENSIONS
            weights = {d: 1.0 for d in dims}

        scores = {}
        winners = []
        losers = []

        for script_id, dim_scores in probe_results.items():
            label = self.benchmark.get(script_id)
            if not label:
                continue

            w_sum = sum(dim_scores.get(d, 0) * w for d, w in weights.items() if w > 0)
            w_tot = sum(w for d, w in weights.items() if w > 0 and d in dim_scores)
            if w_tot > 0:
                scores[script_id] = w_sum / w_tot
                if label == "winner":
                    winners.append(script_id)
                else:
                    losers.append(script_id)

        total = len(winners) * len(losers)
        correct = sum(1 for w in winners for l in losers if scores.get(w, 0) > scores.get(l, 0))
        pairwise_acc = correct / total if total > 0 else 0.0

        k = max(1, int(len(scores) * 0.1))
        top_k = sorted(scores, key=lambda s: scores[s], reverse=True)[:k]
        top_winners = sum(1 for s in top_k if s in set(winners))
        top10 = top_winners / k if k > 0 else 0.0

        return pairwise_acc, top10

    def optimize_probe_weights(self, probe_results: Dict,
                                n_trials: int = 100) -> Tuple[Dict, float]:
        """
        Quick weight optimization on probe results (free, no LLM calls).
        Returns (best_weights, best_accuracy).
        """
        dims = list(next(iter(probe_results.values())).keys()) if probe_results else V2_DIMENSIONS
        rng = random.Random(42)
        weight_options = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]

        best_weights  = {d: 1.0 for d in dims}
        best_acc, _   = self.score_probe_accuracy(probe_results, best_weights)

        for _ in range(n_trials):
            w = {d: rng.choice(weight_options) for d in dims}
            if not any(v > 0 for v in w.values()):
                continue
            acc, _ = self.score_probe_accuracy(probe_results, w)
            if acc > best_acc:
                best_acc = acc
                best_weights = w

        return best_weights, best_acc

    def estimated_cost(self) -> float:
        return len(self.probe_ids) * COST_PER_SCRIPT
