"""
Intelligently discover and propose new facets for evaluation.
Analyzes current performance to identify gaps and propose new dimensions.
"""
import json
from typing import List, Dict
from pathlib import Path


class FacetDiscoverer:
    """Discover new facet proposals by analyzing performance gaps"""

    def __init__(self, per_script_dir: str, benchmark_path: str):
        self.per_script_dir = per_script_dir
        self.benchmark_path = benchmark_path
        self.all_results = {}
        self.benchmark = {}

    def load_data(self):
        """Load results and benchmark"""
        for json_file in Path(self.per_script_dir).glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                    script_id = data.get("script_id")
                    if script_id:
                        self.all_results[script_id] = data
            except:
                pass

        with open(self.benchmark_path) as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    script_id = entry.get("script_id")
                    label = entry.get("label")
                    if script_id and label in ["winner", "loser"]:
                        self.benchmark[script_id] = label
                except:
                    pass

        print(f"Loaded {len(self.all_results)} results, {len(self.benchmark)} labels")

    def analyze_misclassifications(self, current_facets: List[str]) -> Dict:
        """Analyze false positives and false negatives"""
        false_positives = []  # High score, loser
        false_negatives = []  # Low score, winner

        for script_id, result in self.all_results.items():
            label = self.benchmark.get(script_id)
            if not label:
                continue

            agg_score = result.get("aggregated", {}).get("weighted_average", 0)
            individual_scores = result.get("aggregated", {}).get("individual_scores", {})

            if label == "loser" and agg_score >= 7.5:
                false_positives.append({
                    "script_id": script_id,
                    "score": agg_score,
                    "scores": individual_scores
                })
            elif label == "winner" and agg_score < 6.0:
                false_negatives.append({
                    "script_id": script_id,
                    "score": agg_score,
                    "scores": individual_scores
                })

        return {
            "false_positives": false_positives[:5],  # Top 5
            "false_negatives": false_negatives[:5],
            "fp_count": len(false_positives),
            "fn_count": len(false_negatives)
        }

    def generate_facet_proposals(self, current_facets: List[str]) -> List[Dict]:
        """Generate proposals for new facets to test"""
        proposals = []

        # Proposal 1: Narrative Structure / Story Mechanics
        proposals.append({
            "facet_name": "narrative_structure",
            "description": "Strength of plot mechanics, story setup, narrative hooks",
            "evaluation_guide": """Rate 1-10:
            - Does the pilot set up compelling dramatic questions?
            - Is the narrative structure engaging (teaser, act breaks, climax)?
            - Are the stakes clear and immediate?
            - Does the premise create sustainable story potential?
            """,
            "hypothesis": "Great premises aren't enough; transcendent shows have tight narrative construction from page 1",
            "cost": "$0.015 per script",
            "rationale": "Some winners may have strong narrative but our current facets miss story mechanics"
        })

        # Proposal 2: Protagonist Specificity
        proposals.append({
            "facet_name": "protagonist_specificity",
            "description": "How specific, unique, and contradictory is the lead character?",
            "evaluation_guide": """Rate 1-10:
            - Is the protagonist unlike familiar archetypes?
            - Do they have internal contradictions that create friction?
            - Is there a clear why-now moment or motivation that feels earned?
            - Could this character exist in multiple genres (specificity + universality)?
            """,
            "hypothesis": "Character_depth was weak, but protagonist-specificity (not ensemble depth) might be strong",
            "cost": "$0.015 per script",
            "rationale": "Maybe we need to zoom in on the lead vs. evaluating all characters"
        })

        # Proposal 3: Tonal Clarity & Commitment
        proposals.append({
            "facet_name": "tonal_clarity",
            "description": "Does the script know what tone it's operating in and commit to it?",
            "evaluation_guide": """Rate 1-10:
            - Is there a clear tonal identity (dark comedy, prestige drama, thriller)?
            - Does the script maintain tonal commitment or does it waver?
            - Are tonal shifts intentional and earned?
            - Can you identify this show by tone alone?
            """,
            "hypothesis": "Emotional_specificity covers some of this, but tonal mastery might be its own signal",
            "cost": "$0.015 per script",
            "rationale": "Transcendent shows have unmistakable tone; competent shows are tone-confused"
        })

        # Proposal 4: Originality of Problem / Conflict
        proposals.append({
            "facet_name": "conflict_originality",
            "description": "How fresh/unexpected is the central dramatic conflict?",
            "evaluation_guide": """Rate 1-10:
            - Is the core conflict we haven't seen a hundred times?
            - Does it arise organically from character + world (not imposed)?
            - Is there a unique angle or approach to the problem?
            - Would the pitch be exciting to a producer?
            """,
            "hypothesis": "World_originality covers setting but not the originality of what the conflict actually IS",
            "cost": "$0.015 per script",
            "rationale": "Transcendent shows have novel central tensions, not just novel worlds"
        })

        # Proposal 5: Visual Language / Cinematic Potential
        proposals.append({
            "facet_name": "visual_language",
            "description": "Does the script describe visual storytelling, blocking, or cinematic choices?",
            "evaluation_guide": """Rate 1-10:
            - Are there specific visual descriptions or images mentioned?
            - Does the script show cinematic thinking (camera, blocking, production design)?
            - Would a designer/cinematographer have something to latch onto?
            - Does the visual approach match the tone?
            """,
            "hypothesis": "Scripts with strong visual language may predict directorial interest and prestige potential",
            "cost": "$0.015 per script",
            "rationale": "Transcendent shows are visually distinctive; this might not be fully captured"
        })

        # Proposal 6: Ensemble Texture (not depth)
        proposals.append({
            "facet_name": "ensemble_texture",
            "description": "Does the world feel lived-in and populated, with distinct voices?",
            "evaluation_guide": """Rate 1-10:
            - Are secondary characters distinct and memorable?
            - Does each have a voice/perspective that differs from the lead?
            - Is there texture and life in the world, not just the protagonist?
            - Do interactions feel specific, not generic?
            """,
            "hypothesis": "Character_depth was too broad; maybe ensemble-texture (texture not depth) is the signal",
            "cost": "$0.015 per script",
            "rationale": "Transcendent shows have rich ensembles; we may have mislabeled character_depth"
        })

        # Proposal 7: Genre Mastery / Subversion
        proposals.append({
            "facet_name": "genre_mastery",
            "description": "Does the script master or subvert its genre in interesting ways?",
            "evaluation_guide": """Rate 1-10:
            - Does it understand genre conventions deeply?
            - Does it subvert expectations in earned ways?
            - Is the genre choice surprising or inevitable?
            - Would a genre fan find it fresh or predictable?
            """,
            "hypothesis": "Some winners may blend/subvert genres in ways our current facets don't capture",
            "cost": "$0.015 per script",
            "rationale": "Boldness + singular_vision might miss genre-specific mastery"
        })

        # Proposal 8: Dialogue Wit & Specificity (vs. just dialogue_language)
        proposals.append({
            "facet_name": "dialogue_wit",
            "description": "Are individual lines memorable, funny, or revealing in specific ways?",
            "evaluation_guide": """Rate 1-10:
            - Are there moments of wit, humor, or insight in the dialogue?
            - Do lines reveal character in economical ways?
            - Would someone quote this show?
            - Is the wit earned or forced?
            """,
            "hypothesis": "Dialogue_language (7% weight) is weak; maybe wit/specificity is stronger signal",
            "cost": "$0.015 per script",
            "rationale": "Transcendent shows have quotable, memorable dialogue; ours might be buried"
        })

        return proposals

    def print_proposals(self, proposals: List[Dict]):
        """Pretty print proposals"""
        print("\n" + "="*100)
        print("PROPOSED NEW FACETS FOR DISCOVERY")
        print("="*100 + "\n")

        for i, prop in enumerate(proposals, 1):
            print(f"PROPOSAL {i}: {prop['facet_name'].upper()}")
            print(f"Description: {prop['description']}")
            print(f"Hypothesis: {prop['hypothesis']}")
            print(f"Rationale: {prop['rationale']}")
            print(f"Cost: {prop['cost']}")
            print(f"\nEvaluation Guide:")
            print(prop['evaluation_guide'])
            print("-" * 100)


if __name__ == "__main__":
    discoverer = FacetDiscoverer(
        per_script_dir="./autoresearch/data/results/live/per_script",
        benchmark_path="./autoresearch/data/benchmark/benchmark.jsonl"
    )

    discoverer.load_data()
    proposals = discoverer.generate_facet_proposals([])
    discoverer.print_proposals(proposals)

    # Save proposals
    with open("./autoresearch/data/results/facet_discovery_proposals.json", "w") as f:
        json.dump(proposals, f, indent=2)
    print("Saved proposals to facet_discovery_proposals.json")
