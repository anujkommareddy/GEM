"""
Re-evaluate all scripts with v2.0 (producer-mind) rubric.
Single LLM pass per script with 5 dimensions.
"""
import json
import os
from pathlib import Path
from datetime import datetime
import time
import logging
from typing import Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ScreenplayEvaluatorV2:
    """Evaluate scripts with producer-mind rubric v2.0"""

    def __init__(self, config_path: str = None, model: str = "openai"):
        self.model = model
        self.rubric = self._load_rubric()
        self._init_client()

    def _load_rubric(self) -> str:
        """Load v2.0 rubric"""
        with open("./autoresearch/config/rubric_v2_producer_mind.md") as f:
            return f.read()

    def _init_client(self):
        """Initialize LLM client"""
        import openai
        self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model_name = "gpt-5-mini"
        logger.info(f"Initialized OpenAI/gpt-5-mini evaluator")

    def evaluate(self, script_id: str, script_text: str) -> Dict:
        """
        Evaluate a screenplay with v2.0 rubric (single LLM pass).

        Returns JSON with:
        - script_id
        - model
        - timestamp
        - scores for 5 dimensions
        - summary
        - status
        """

        prompt = f"""{self.rubric}

---

## Script to Evaluate

**Script ID:** {script_id}

**Full Script Text:**

{script_text[:15000]}  <!-- Truncate to first ~15k chars if needed -->

---

## Your Evaluation

Please provide a JSON evaluation following the Output Format above. Score each dimension 1-10 with reasoning. Provide a brief summary.

Return ONLY valid JSON, no other text."""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=2000,
                timeout=120
            )
            result_text = response.choices[0].message.content

            # Parse JSON from response
            try:
                # Try to extract JSON if wrapped in markdown code blocks
                if "```json" in result_text:
                    json_str = result_text.split("```json")[1].split("```")[0]
                elif "```" in result_text:
                    json_str = result_text.split("```")[1].split("```")[0]
                else:
                    json_str = result_text

                scores = json.loads(json_str)

                return {
                    "script_id": script_id,
                    "model": self.model,
                    "timestamp": datetime.utcnow().isoformat(),
                    "v2_scores": {
                        "audience_appeal_marketability": scores.get("audience_appeal_marketability", {}),
                        "conceptual_hook_clarity": scores.get("conceptual_hook_clarity", {}),
                        "character_appeal_and_long_term_potential": scores.get("character_appeal_and_long_term_potential", {}),
                        "creative_originality_and_boldness": scores.get("creative_originality_and_boldness", {}),
                        "narrative_momentum_engagement": scores.get("narrative_momentum_engagement", {})
                    },
                    "summary": scores.get("summary", ""),
                    "status": "success"
                }

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON for {script_id}: {e}")
                logger.debug(f"Response was: {result_text[:500]}")
                return {
                    "script_id": script_id,
                    "model": self.model,
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "parse_error",
                    "error": str(e)
                }

        except Exception as e:
            logger.error(f"Evaluation failed for {script_id}: {e}")
            return {
                "script_id": script_id,
                "model": self.model,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "error",
                "error": str(e)
            }


class EvaluationOrchestrator:
    """Orchestrate re-evaluation of 909 scripts"""

    def __init__(self, per_script_dir: str, extracted_text_dir: str, output_dir: str):
        self.per_script_dir = per_script_dir
        self.extracted_text_dir = extracted_text_dir
        self.output_dir = output_dir
        self.evaluator = ScreenplayEvaluatorV2(model="openai")
        self.results = []

    def load_extracted_text(self, script_id: str) -> Optional[str]:
        """Load extracted text for a script"""
        # Try multiple filename formats
        for fname in [f"{script_id}.txt", f"{script_id}.md"]:
            path = Path(self.extracted_text_dir) / fname
            if path.exists():
                try:
                    with open(path) as f:
                        return f.read()
                except:
                    pass
        return None

    def run_evaluation(self, max_scripts: int = None, skip_existing: bool = True):
        """Run evaluation on all scripts"""
        # Find all script IDs from per_script results
        script_ids = set()
        for json_file in Path(self.per_script_dir).glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                    script_id = data.get("script_id")
                    if script_id:
                        script_ids.add(script_id)
            except:
                pass

        script_ids = sorted(list(script_ids))
        if max_scripts:
            script_ids = script_ids[:max_scripts]

        logger.info(f"Evaluating {len(script_ids)} scripts with v2.0 rubric")

        evaluated = 0
        skipped = 0
        errors = 0

        for i, script_id in enumerate(script_ids, 1):
            # Skip if already v2 evaluated
            if skip_existing:
                v2_results_dir = Path(self.output_dir) / "v2_results"
                v2_results_dir.mkdir(exist_ok=True)
                v2_file = v2_results_dir / f"{script_id}_v2.json"
                if v2_file.exists():
                    skipped += 1
                    continue

            # Load extracted text
            text = self.load_extracted_text(script_id)
            if not text:
                logger.warning(f"Could not load text for {script_id}")
                errors += 1
                continue

            # Evaluate
            result = self.evaluator.evaluate(script_id, text)

            # Save result
            v2_results_dir = Path(self.output_dir) / "v2_results"
            v2_results_dir.mkdir(exist_ok=True)
            with open(v2_results_dir / f"{script_id}_v2.json", "w") as f:
                json.dump(result, f, indent=2)

            evaluated += 1
            self.results.append(result)

            # Progress
            if i % 50 == 0:
                logger.info(f"Progress: {i}/{len(script_ids)} ({evaluated} evaluated, {skipped} skipped, {errors} errors)")

            # Rate limiting
            time.sleep(0.5)

        logger.info(f"\nEvaluation complete:")
        logger.info(f"  Evaluated: {evaluated}")
        logger.info(f"  Skipped: {skipped}")
        logger.info(f"  Errors: {errors}")
        logger.info(f"  Total: {evaluated + skipped + errors}")

        self._save_summary()

    def _save_summary(self):
        """Save evaluation summary"""
        successful = [r for r in self.results if r.get("status") == "success"]

        summary = {
            "total_evaluated": len(self.results),
            "successful": len(successful),
            "failed": len(self.results) - len(successful),
            "timestamp": datetime.utcnow().isoformat(),
            "model": self.evaluator.model,
            "rubric_version": "v2.0_producer_mind",
            "dimension_names": [
                "audience_appeal_marketability",
                "conceptual_hook_clarity",
                "character_appeal_and_long_term_potential",
                "creative_originality_and_boldness",
                "narrative_momentum_engagement"
            ]
        }

        summary_path = Path(self.output_dir) / "v2_evaluation_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Summary saved to {summary_path}")


if __name__ == "__main__":
    orchestrator = EvaluationOrchestrator(
        per_script_dir="./autoresearch/data/results/live/per_script",
        extracted_text_dir="./autoresearch/data/extracted_text",
        output_dir="./autoresearch/data/results"
    )

    print("""
    =============================================================================
    RE-EVALUATION WITH V2.0 (PRODUCER MIND) RUBRIC
    =============================================================================

    This will:
    1. Load all 909 scripts from extracted_text directory
    2. Evaluate each with GPT-5-mini using v2.0 rubric (single pass)
    3. Save results to v2_results/ directory
    4. Cost: ~$14

    Ready to proceed? (This will take 1-2 hours)
    """)

    # orchestrator.run_evaluation()  # Uncomment to run

