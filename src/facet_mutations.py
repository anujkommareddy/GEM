"""
Test no-cost facet mutations: remove, merge, reweight.
These don't require LLM calls - just re-aggregate existing scores.
"""
import json
import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class FacetMutation:
    """A proposed facet set mutation"""
    mutation_id: int
    name: str
    facets: List[str]  # New facet set (subset, merged, or same)
    weights: Dict[str, float]  # Weights for new facet set
    rationale: str
    cost: str  # "$0", "$0", etc.


class FacetMutator:
    """Generate mutations that don't require LLM calls"""

    # Best weights from Phase 1
    PHASE1_BEST_WEIGHTS = {
        "singular_vision": 0.4273851854533774,
        "boldness": 0.20259790463915314,
        "world_originality": 0.15399934312901412,
        "emotional_specificity": 0.12246222048555838,
        "thematic_ambition": 0.051698630201739704,
        "dialogue_language": 0.03304176744228611,
        "character_depth": 0.00881494864887126,
    }

    ALL_FACETS = list(PHASE1_BEST_WEIGHTS.keys())

    def __init__(self):
        self.mutations = []

    def generate_mutations(self) -> List[FacetMutation]:
        """Generate mutations to test"""
        self.mutations = []
        mutation_id = 0

        # M0: Current best (control)
        current_facets = list(self.PHASE1_BEST_WEIGHTS.keys())
        self.mutations.append(FacetMutation(
            mutation_id=mutation_id,
            name="Current best (Phase 1 - P8)",
            facets=current_facets,
            weights=self.PHASE1_BEST_WEIGHTS.copy(),
            rationale="Control: quadratic gap scaling on all 7 facets",
            cost="$0"
        ))
        mutation_id += 1

        # M1: Remove character_depth (weakest signal)
        facets_no_char = [f for f in self.ALL_FACETS if f != "character_depth"]
        weights_no_char = {f: self.PHASE1_BEST_WEIGHTS[f] for f in facets_no_char}
        total = sum(weights_no_char.values())
        weights_no_char = {f: w/total for f, w in weights_no_char.items()}
        self.mutations.append(FacetMutation(
            mutation_id=mutation_id,
            name="Remove character_depth (6-facet)",
            facets=facets_no_char,
            weights=weights_no_char,
            rationale="Drop lowest-gap facet; renormalize remaining weights",
            cost="$0"
        ))
        mutation_id += 1

        # M2: Remove dialogue_language (second weakest)
        facets_no_dialogue = [f for f in self.ALL_FACETS if f != "dialogue_language"]
        weights_no_dialogue = {f: self.PHASE1_BEST_WEIGHTS[f] for f in facets_no_dialogue}
        total = sum(weights_no_dialogue.values())
        weights_no_dialogue = {f: w/total for f, w in weights_no_dialogue.items()}
        self.mutations.append(FacetMutation(
            mutation_id=mutation_id,
            name="Remove dialogue_language (6-facet)",
            facets=facets_no_dialogue,
            weights=weights_no_dialogue,
            rationale="Drop second-lowest-gap facet; renormalize",
            cost="$0"
        ))
        mutation_id += 1

        # M3: Remove both character_depth and dialogue_language (5-facet)
        facets_5 = [f for f in self.ALL_FACETS if f not in ["character_depth", "dialogue_language"]]
        weights_5 = {f: self.PHASE1_BEST_WEIGHTS[f] for f in facets_5}
        total = sum(weights_5.values())
        weights_5 = {f: w/total for f, w in weights_5.items()}
        self.mutations.append(FacetMutation(
            mutation_id=mutation_id,
            name="Remove both weak facets (5-facet)",
            facets=facets_5,
            weights=weights_5,
            rationale="Keep only the 5 highest-gap facets; renormalize",
            cost="$0"
        ))
        mutation_id += 1

        # M4: Merge dialogue_language + thematic_ambition (treat as one averaged score)
        # This means we use the average of the two scores, so we drop both from individual
        # and treat their combined weight as the aggregate
        facets_merged = [f for f in self.ALL_FACETS if f not in ["dialogue_language", "thematic_ambition"]]
        facets_merged.append("dialogue+thematic_merged")
        weights_merged = {f: self.PHASE1_BEST_WEIGHTS[f] for f in self.ALL_FACETS
                         if f not in ["dialogue_language", "thematic_ambition"]}
        # Combined weight for merged facet
        weights_merged["dialogue+thematic_merged"] = self.PHASE1_BEST_WEIGHTS["dialogue_language"] + self.PHASE1_BEST_WEIGHTS["thematic_ambition"]
        self.mutations.append(FacetMutation(
            mutation_id=mutation_id,
            name="Merge dialogue + thematic (6-facet)",
            facets=facets_merged,
            weights=weights_merged,
            rationale="Combine dialogue_language and thematic_ambition into one averaged score (if they're correlated)",
            cost="$0"
        ))
        mutation_id += 1

        # M5: Re-balance Phase 1 best more aggressively
        # (make top 3 even more dominant)
        aggressive_weights = {
            "singular_vision": 0.50,
            "boldness": 0.25,
            "world_originality": 0.12,
            "emotional_specificity": 0.08,
            "thematic_ambition": 0.03,
            "dialogue_language": 0.01,
            "character_depth": 0.01,
        }
        self.mutations.append(FacetMutation(
            mutation_id=mutation_id,
            name="Aggressive rebalancing (favor top 3)",
            facets=self.ALL_FACETS,
            weights=aggressive_weights,
            rationale="Give even more weight to singular_vision + boldness, minimize weak ones",
            cost="$0"
        ))
        mutation_id += 1

        # M6: Sparse + high-gap only (3 facets: singular_vision, boldness, world_originality)
        facets_top3 = ["singular_vision", "boldness", "world_originality"]
        weights_top3 = {f: 1/3 for f in facets_top3}
        self.mutations.append(FacetMutation(
            mutation_id=mutation_id,
            name="Sparse top-3 only (3-facet)",
            facets=facets_top3,
            weights=weights_top3,
            rationale="Only score the 3 facets with highest winner-loser gaps; equal weight",
            cost="$0"
        ))
        mutation_id += 1

        return self.mutations

    def print_mutations(self):
        """Print all mutations"""
        print("\n" + "="*100)
        print("PHASE 2a: NO-COST FACET MUTATIONS (Remove, Merge, Reweight)")
        print("="*100)
        for mut in self.mutations:
            print(f"\nM{mut.mutation_id}: {mut.name}")
            print(f"  Facets: {mut.facets}")
            print(f"  Weights: {json.dumps(mut.weights, indent=14)}")
            print(f"  Rationale: {mut.rationale}")
            print(f"  Cost: {mut.cost}")
        print("="*100 + "\n")


if __name__ == "__main__":
    mutator = FacetMutator()
    mutations = mutator.generate_mutations()
    mutator.print_mutations()

    # Save for Phase 2
    mutations_data = [
        {
            "mutation_id": m.mutation_id,
            "name": m.name,
            "facets": m.facets,
            "weights": m.weights,
            "rationale": m.rationale,
            "cost": m.cost
        }
        for m in mutations
    ]
    with open("./autoresearch/data/results/facet_mutations_phase2a.json", "w") as f:
        json.dump(mutations_data, f, indent=2)
    print("Saved mutations to facet_mutations_phase2a.json")
