"""Screenplay evaluator using LLM-based scoring."""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
import os

logger = logging.getLogger(__name__)


class ScreenplayEvaluator:
    """Evaluate screenplays using Claude or OpenAI LLM."""

    def __init__(self, config, model_name: str = None):
        """
        Initialize evaluator.

        Args:
            config: Config object with rubric and model settings
            model_name: Which model to use (claude, openai). Defaults to config default.
        """
        self.config = config
        self.model_name = model_name or config.get("models.default")

        # Load prompts
        self.rubric = config.load_rubric()
        self.extraction_prompt = config.load_extraction_prompt()

        # Initialize LLM client
        self._init_client()

    def _init_client(self):
        """Initialize appropriate LLM client."""
        if self.model_name == "claude":
            try:
                import anthropic
            except ImportError:
                raise ImportError("Anthropic library not installed. Install with: pip install anthropic")
            self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            self.model_config = self.config.get_model_config("claude")
        elif self.model_name == "openai":
            # OpenAI support - for now, using basic compatibility
            try:
                import openai

                self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                self.model_config = self.config.get_model_config("openai")
            except ImportError:
                raise ImportError("OpenAI library not installed. Install with: pip install openai")
        else:
            raise ValueError(f"Unknown model: {self.model_name}")

        logger.info(f"Initialized {self.model_name} client")

    def evaluate(self, script_id: str, script_text: str) -> Dict:
        """
        Evaluate a screenplay.

        If v2.0 rubric is loaded (producer-mind), does single-pass evaluation.
        Otherwise does 2-pass (extraction + scoring).

        Args:
            script_id: Unique identifier for script
            script_text: Full screenplay text

        Returns:
            Evaluation result dictionary
        """
        logger.info(f"Evaluating {script_id} with {self.model_name}...")

        try:
            # Check if v2.0 rubric (producer-mind) - if so, single pass
            is_v2 = "Producer-Grounded Evaluation" in self.rubric

            if is_v2:
                # V2.0: Single LLM pass with all 5 dimensions
                scoring = self._score_dimensions_v2(script_id, script_text)
                aggregated = self._aggregate_scores_v2(scoring)

                result = {
                    "script_id": script_id,
                    "model": self.model_name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "scoring": scoring,
                    "aggregated": aggregated,
                    "status": "success",
                }
            else:
                # V1: 2-pass evaluation (extraction + scoring)
                extraction = self._extract_features(script_id, script_text)
                logger.debug(f"Feature extraction complete for {script_id}")

                scoring = self._score_dimensions(script_id, script_text, extraction)
                logger.debug(f"Dimension scoring complete for {script_id}")

                aggregated = self._aggregate_scores(scoring)

                result = {
                    "script_id": script_id,
                    "model": self.model_name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "extraction": extraction,
                    "scoring": scoring,
                    "aggregated": aggregated,
                    "status": "success",
                }

            return result

        except Exception as e:
            logger.error(f"Evaluation failed for {script_id}: {e}")
            return {
                "script_id": script_id,
                "model": self.model_name,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "error",
                "error": str(e),
            }

    def _extract_features(self, script_id: str, script_text: str) -> Dict:
        """Extract key features from screenplay."""
        # Truncate long scripts to avoid token limits
        truncated_text = script_text[: 50000]  # ~12k tokens

        messages = [
            {
                "role": "user",
                "content": f"{self.extraction_prompt}\n\n--- SCREENPLAY TEXT ---\n\n{truncated_text}",
            }
        ]

        response = self._call_model(messages)

        try:
            # Try to parse JSON from response
            result_text = response
            json_start = result_text.find("{")
            json_end = result_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = result_text[json_start:json_end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse extraction JSON for {script_id}")
            return {"script_id": script_id, "extraction_error": "Failed to parse response"}

        return {"script_id": script_id, "raw_response": response[:500]}

    def _score_dimensions(self, script_id: str, script_text: str, extraction: Dict) -> Dict:
        """Score each evaluation dimension."""
        # Truncate script again
        truncated_text = script_text[: 40000]

        # Prepare context from extraction
        extraction_summary = json.dumps(extraction, indent=2)[:2000]

        messages = [
            {
                "role": "user",
                "content": f"{self.rubric}\n\n--- EXTRACTED FEATURES ---\n{extraction_summary}\n\n--- SCREENPLAY EXCERPT ---\n\n{truncated_text}",
            }
        ]

        response = self._call_model(messages)

        try:
            # Parse JSON from response
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"Could not parse scoring JSON for {script_id}")

        return {"script_id": script_id, "error": "Failed to parse scores"}

    def _aggregate_scores(self, scoring: Dict) -> Dict:
        """Aggregate individual dimension scores."""
        dimensions = self.config.get("evaluation.dimensions", [])
        weights = self.config.evaluator_config.get("weights", {})

        scores = {}
        total_weight = 0
        weighted_sum = 0

        for dim in dimensions:
            if dim == "transcendence_verdict":
                continue  # Don't aggregate the final verdict into itself

            if dim in scoring and isinstance(scoring[dim], dict):
                score = scoring[dim].get("score")
                if score is not None:
                    weight = weights.get(dim, 1.0 / len(dimensions))
                    scores[dim] = score
                    weighted_sum += score * weight
                    total_weight += weight

        final_score = weighted_sum / total_weight if total_weight > 0 else 0

        return {
            "individual_scores": scores,
            "weighted_average": round(final_score, 2),
            "scale": "1-10",
            "recommendation_category": self._categorize_score(final_score),
        }

    def _categorize_score(self, score: float) -> str:
        """Categorize score into transcendence level."""
        if score >= 8.5:
            return "Transcendent"
        elif score >= 7.0:
            return "Exceptional"
        elif score >= 5.5:
            return "Promising"
        elif score >= 4.0:
            return "Competent"
        else:
            return "Generic"

    def _call_model(self, messages: List[Dict], max_retries: int = 3) -> str:
        """Call the LLM and return text response. Retries on timeout/transient errors."""
        for attempt in range(1, max_retries + 1):
            try:
                if self.model_name == "claude":
                    response = self.client.messages.create(
                        model=self.model_config.get("model", "claude-opus-4-6"),
                        max_tokens=self.model_config.get("max_tokens", 2000),
                        temperature=self.model_config.get("temperature", 0.7),
                        messages=messages,
                        timeout=120.0,
                    )
                    return response.content[0].text

                elif self.model_name == "openai":
                    response = self.client.chat.completions.create(
                        model=self.model_config.get("model", "gpt-4"),
                        max_completion_tokens=self.model_config.get("max_tokens", 2000),
                        messages=messages,
                        timeout=120.0,
                    )
                    return response.choices[0].message.content

            except Exception as e:
                err_str = str(e).lower()
                is_retryable = any(k in err_str for k in ["timeout", "connection", "rate", "503", "529", "500"])
                if is_retryable and attempt < max_retries:
                    wait = 2 ** attempt
                    logger.warning(f"Attempt {attempt} failed ({e}), retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                raise

    def _score_dimensions_v2(self, script_id: str, script_text: str) -> Dict:
        """V2.0: Single-pass evaluation with 5 dimensions (producer-mind rubric)."""
        truncated_text = script_text[:15000]  # Truncate for token limits

        prompt = f"""{self.rubric}

---

## Script to Evaluate

**Script ID:** {script_id}

**Full Script Text:**

{truncated_text}

---

## Your Evaluation

Please provide a JSON evaluation following the Output Format above. Score each dimension 1-10 with reasoning. Provide a brief summary.

Return ONLY valid JSON, no other text."""

        messages = [{"role": "user", "content": prompt}]
        response = self._call_model(messages)

        try:
            # Parse JSON (handle markdown code blocks)
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response

            parsed = json.loads(json_str)

            # Extract scores for v2.0 dimensions
            scoring = {
                "audience_appeal_marketability": parsed.get("audience_appeal_marketability", {}),
                "conceptual_hook_clarity": parsed.get("conceptual_hook_clarity", {}),
                "character_appeal_and_long_term_potential": parsed.get("character_appeal_and_long_term_potential", {}),
                "creative_originality_and_boldness": parsed.get("creative_originality_and_boldness", {}),
                "narrative_momentum_engagement": parsed.get("narrative_momentum_engagement", {}),
            }

            return scoring

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse v2.0 scores for {script_id}: {e}")
            raise

    def _aggregate_scores_v2(self, scoring: Dict) -> Dict:
        """V2.0: Aggregate 5 dimension scores with equal weighting."""
        scores = {}
        dimension_scores = []

        for dimension, score_obj in scoring.items():
            if isinstance(score_obj, dict):
                score = score_obj.get("score", 0)
            else:
                score = float(score_obj)
            scores[dimension] = score
            dimension_scores.append(score)

        # Simple average for v2.0
        avg_score = sum(dimension_scores) / len(dimension_scores) if dimension_scores else 0

        return {
            "individual_scores": scores,
            "weighted_average": round(avg_score, 2),
            "scale": "1-10",
            "recommendation_category": self._categorize_score(avg_score),
        }

    def evaluate_batch(self, script_list: List[tuple]) -> List[Dict]:
        """
        Evaluate multiple scripts.

        Args:
            script_list: List of (script_id, script_text) tuples

        Returns:
            List of evaluation results
        """
        results = []
        for i, (script_id, script_text) in enumerate(script_list, 1):
            logger.info(f"[{i}/{len(script_list)}] Evaluating {script_id}...")
            result = self.evaluate(script_id, script_text)
            results.append(result)

        return results
