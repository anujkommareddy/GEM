"""
Evaluate newly proposed facets on samples, decide which to roll out fully.
"""
import json
import os
from pathlib import Path
import random
from typing import Dict, List
import sys

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class FacetEvaluationRunner:
    """Test new facets on samples before full rollout"""

    NEW_FACET_PROMPTS = {
        "narrative_structure": {
            "description": "Strength of plot mechanics, story setup, narrative hooks",
            "prompt": """Rate this screenplay's NARRATIVE STRUCTURE on a 1-10 scale:

Consider:
- Does the pilot set up compelling dramatic questions immediately?
- Is the narrative structure engaging (teaser, act breaks, climax)?
- Are the stakes clear and immediate for the audience?
- Does the premise create sustainable story potential for multiple seasons?
- Is the setup efficient and well-paced?

Score 9-10: Masterful narrative structure; tight setup with clear questions and stakes
Score 7-8: Strong structure; clear dramatic questions and momentum
Score 5-6: Competent structure; clear stakes but may feel formulaic
Score 3-4: Weak structure; unclear stakes or pacing issues
Score 1-2: Broken structure; confusing or unengaging setup

Return JSON: {"narrative_structure": <score>, "reasoning": "<2-3 sentences>"}"""
        },

        "protagonist_specificity": {
            "description": "How specific, unique, and contradictory is the lead character?",
            "prompt": """Rate this screenplay's PROTAGONIST SPECIFICITY on a 1-10 scale:

Consider:
- Is the lead character fundamentally unlike common archetypes?
- Does the protagonist have internal contradictions that create dramatic friction?
- Is there a clear, earned motivation for why-now (why this story now)?
- Does the character feel both universal and deeply specific?
- Could you describe this character in 2-3 sentences and have a producer immediately get it?

Score 9-10: Unforgettable, specific protagonist with rich contradictions
Score 7-8: Distinct character with clear contradictions and motivation
Score 5-6: Recognizable character archetype with some specificity
Score 3-4: Familiar archetype with limited distinctiveness
Score 1-2: Generic or underdeveloped protagonist

Return JSON: {"protagonist_specificity": <score>, "reasoning": "<2-3 sentences>"}"""
        },

        "tonal_clarity": {
            "description": "Does the script know its tone and commit to it?",
            "prompt": """Rate this screenplay's TONAL CLARITY on a 1-10 scale:

Consider:
- Is there a clear tonal identity (prestige drama, dark comedy, thriller, etc.)?
- Does the script maintain tonal commitment or does it waver inconsistently?
- Are tonal shifts intentional and earned by the story?
- Could you identify this show's tone from dialogue/scenes alone?
- Is the tone distinctive or generic?

Score 9-10: Unmistakable, masterful tone maintained throughout
Score 7-8: Clear tone with confident execution
Score 5-6: Identifiable tone but with some wavering
Score 3-4: Uncertain tone; mixed signals about what kind of show this is
Score 1-2: Confused or absent tonal identity

Return JSON: {"tonal_clarity": <score>, "reasoning": "<2-3 sentences>"}"""
        },

        "conflict_originality": {
            "description": "How fresh/unexpected is the central dramatic conflict?",
            "prompt": """Rate this screenplay's CONFLICT ORIGINALITY on a 1-10 scale:

Consider:
- Is the core conflict genuinely fresh or have we seen it 100 times?
- Does the conflict arise organically from character + world (not imposed)?
- Is there a unique angle or approach to the central problem?
- Could a producer get excited about this specific conflict?
- Does it avoid being a procedural or generic setup?

Score 9-10: Genuinely novel central conflict; haven't seen this angle before
Score 7-8: Fresh approach to conflict; strong unique perspective
Score 5-6: Competent conflict setup with some originality
Score 3-4: Familiar conflict; feels like we've seen this many times
Score 1-2: Generic or clichéd central tension

Return JSON: {"conflict_originality": <score>, "reasoning": "<2-3 sentences>"}"""
        },

        "visual_language": {
            "description": "Visual storytelling potential and cinematic choices",
            "prompt": """Rate this screenplay's VISUAL LANGUAGE on a 1-10 scale:

Consider:
- Does the script describe specific visual elements or images?
- Are there cinematic choices (blocking, camera, production design) indicated?
- Would a cinematographer or production designer have something to latch onto?
- Does the visual approach match and reinforce the tone?
- Is there visual specificity or does it feel bland/generic?

Score 9-10: Rich, specific visual language; would inspire a visual filmmaker
Score 7-8: Strong visual thinking; specific images and cinematic choices
Score 5-6: Some visual description; competent but not distinctive
Score 3-4: Minimal visual language; reads like a TV procedural script
Score 1-2: No visual storytelling; purely dialogue-driven

Return JSON: {"visual_language": <score>, "reasoning": "<2-3 sentences>"}"""
        },

        "ensemble_texture": {
            "description": "Does the world feel lived-in with distinct secondary voices?",
            "prompt": """Rate this screenplay's ENSEMBLE TEXTURE on a 1-10 scale:

Consider:
- Are secondary characters distinct and memorable (not generic)?
- Does each character have a recognizable voice/perspective?
- Does the world feel populated and lived-in, not just focused on the lead?
- Are interactions between characters specific, not generic small talk?
- Would you want to spend time with this ensemble?

Score 9-10: Rich ensemble; everyone has a distinct voice and presence
Score 7-8: Strong secondary characters; interesting ensemble dynamics
Score 5-6: Competent ensemble; characters feel distinct but not memorable
Score 3-4: Weak ensemble; secondary characters feel generic or underdeveloped
Score 1-2: Barely-there ensemble; only lead is developed

Return JSON: {"ensemble_texture": <score>, "reasoning": "<2-3 sentences>"}"""
        },

        "genre_mastery": {
            "description": "Mastery or interesting subversion of genre conventions",
            "prompt": """Rate this screenplay's GENRE MASTERY on a 1-10 scale:

Consider:
- Does the script understand its genre conventions deeply?
- Does it subvert expectations in earned, interesting ways?
- Is the genre choice surprising or inevitable for this story?
- Would genre fans find it fresh or predictable?
- Is the execution confident and specific to the genre?

Score 9-10: Genre mastery; confident, fresh, deeply understood
Score 7-8: Strong genre understanding; some interesting subversions
Score 5-6: Competent genre execution; follows conventions well
Score 3-4: Generic genre execution; feels like many other scripts
Score 1-2: Confused genre identity; doesn't understand what kind of story it is

Return JSON: {"genre_mastery": <score>, "reasoning": "<2-3 sentences>"}"""
        },

        "dialogue_wit": {
            "description": "Memorable, witty, or revealing individual lines",
            "prompt": """Rate this screenplay's DIALOGUE WIT on a 1-10 scale:

Consider:
- Are individual lines memorable, funny, or revealing?
- Do lines reveal character in economical, clever ways?
- Would someone quote this show? Are there quotable moments?
- Is the wit earned or forced/obvious?
- Does dialogue have personality specific to the show's voice?

Score 9-10: Memorable, witty dialogue; quotes jump out at you
Score 7-8: Strong individual lines; clever character reveals
Score 5-6: Competent dialogue; clear but not particularly witty
Score 3-4: Generic dialogue; feels like many other shows
Score 1-2: Poor dialogue; clunky or purely functional

Return JSON: {"dialogue_wit": <score>, "reasoning": "<2-3 sentences>"}"""
        }
    }

    def __init__(self, results_dir: str):
        self.results_dir = results_dir

    def generate_facet_evaluation_guide(self, facets_to_test: List[str]) -> str:
        """Generate evaluation guide for new facets"""
        guide = """
# NEW FACET EVALUATION GUIDE

You will evaluate scripts on 8 NEW proposed dimensions that may improve our ability to predict transcendence.

Each facet should be evaluated independently (1-10 scale) and provide reasoning.

---
"""
        for facet in facets_to_test:
            if facet in self.NEW_FACET_PROMPTS:
                info = self.NEW_FACET_PROMPTS[facet]
                guide += f"\n## {facet.upper()}\n"
                guide += f"Description: {info['description']}\n"
                guide += f"Prompt: {info['prompt']}\n"
                guide += "-" * 80 + "\n"

        return guide

    def create_sample_for_evaluation(self, sample_ids: List[str], output_path: str):
        """Create a sample list for manual evaluation"""
        with open(output_path, "w") as f:
            f.write("# Sample Scripts for New Facet Evaluation\n\n")
            f.write(f"Evaluate the following {len(sample_ids)} scripts on the new facets.\n\n")
            for i, script_id in enumerate(sample_ids, 1):
                f.write(f"{i}. {script_id}\n")

    def print_next_steps(self):
        """Print the next steps for continuing autoresearch"""
        print("\n" + "="*100)
        print("NEXT STEPS: EVALUATE NEW FACETS & CONTINUE AUTORESEARCH")
        print("="*100 + "\n")

        print("The autoresearch loop has identified 8 promising new facets to test:")
        print()

        for facet, info in self.NEW_FACET_PROMPTS.items():
            print(f"  • {facet:<25} - {info['description']}")

        print("\nTO CONTINUE AUTORESEARCH:")
        print()
        print("1. Create prompts for evaluating these facets on a 200-script sample")
        print("   Cost: ~$3 (200 scripts × $0.015)")
        print()
        print("2. Evaluate all 200 scripts on each new facet using GPT-5-mini/Claude")
        print("   This will generate new dimension scores stored alongside existing scores")
        print()
        print("3. Load the new scores into per-script JSON files:")
        print("   existing: singular_vision, boldness, world_originality, etc.")
        print("   NEW: narrative_structure, protagonist_specificity, tonal_clarity, etc.")
        print()
        print("4. Resume the autoresearch loop, which will:")
        print("   • Test adding each new facet to the current best config")
        print("   • Compare holdout accuracy: 74.15% (current) vs. with new facet")
        print("   • Keep improvements > 0.2%, reject others")
        print("   • Continue finding optimal combination")
        print()
        print("5. Budget allocation:")
        print("   • Sample evaluation: $3 per new facet × 8 = $24")
        print("   • Full rollout (if promising): $13.63 × promising facets")
        print("   • Estimated total: $40-70 for comprehensive testing")
        print("   • Budget remaining: $186 (plenty of room)")
        print()
        print("RECOMMENDED: Start with top 3 facets (narrative_structure, protagonist_specificity, tonal_clarity)")
        print("Cost: ~$9 for sample evaluation, $41 for full rollout if all promising")
        print()
        print("="*100 + "\n")


if __name__ == "__main__":
    runner = FacetEvaluationRunner(
        results_dir="./autoresearch/data/results"
    )

    # Show evaluation guide
    guide = runner.generate_facet_evaluation_guide(list(runner.NEW_FACET_PROMPTS.keys()))
    print(guide)

    # Save guide
    with open("./autoresearch/data/results/new_facet_evaluation_guide.md", "w") as f:
        f.write(guide)

    # Print next steps
    runner.print_next_steps()
