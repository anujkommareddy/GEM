"""Auto-generate improvement proposals based on dimension analysis."""

import json
from pathlib import Path
from typing import Dict, List, Tuple


class AutoProposer:
    """Generate rubric/weight improvement proposals."""

    # Current baseline weights (from evaluator_config.json)
    BASELINE_WEIGHTS = {
        "singular_vision": 0.25,
        "character_depth": 0.20,
        "thematic_ambition": 0.15,
        "emotional_specificity": 0.15,
        "world_originality": 0.10,
        "dialogue_language": 0.10,
        "boldness": 0.05,
        "transcendence_verdict": 0.0,
    }

    # Per-dimension gaps from latest summary (winner avg - loser avg)
    # Higher gap = better predictor of transcendence
    DIMENSION_GAPS = {
        "singular_vision": 2.20,
        "boldness": 1.98,
        "world_originality": 1.92,
        "emotional_specificity": 1.87,
        "thematic_ambition": 1.74,
        "dialogue_language": 1.69,
        "character_depth": 1.60,
    }

    def __init__(self, summary_file: Path = None):
        """
        Initialize proposer.

        Args:
            summary_file: Optional path to latest_summary.md to extract gaps
        """
        self.summary_file = summary_file
        self.proposals = []

    def propose_weight_increase(self, dimension: str, new_weight: float) -> Dict:
        """
        Propose increasing a dimension's weight.

        Args:
            dimension: Dimension name
            new_weight: New weight value

        Returns:
            Proposal dict
        """
        if dimension not in self.BASELINE_WEIGHTS:
            raise ValueError(f"Unknown dimension: {dimension}")

        current_weight = self.BASELINE_WEIGHTS[dimension]
        gap = self.DIMENSION_GAPS.get(dimension, 0)

        proposal = {
            "type": "weight_increase",
            "dimension": dimension,
            "current_weight": current_weight,
            "new_weight": new_weight,
            "change": new_weight - current_weight,
            "gap_score": gap,
            "rationale": f"Gap of +{gap:.2f} suggests this dimension is a strong predictor. Increasing weight.",
        }

        return proposal

    def propose_weight_decrease(self, dimension: str, new_weight: float) -> Dict:
        """
        Propose decreasing a dimension's weight.

        Args:
            dimension: Dimension name
            new_weight: New weight value

        Returns:
            Proposal dict
        """
        if dimension not in self.BASELINE_WEIGHTS:
            raise ValueError(f"Unknown dimension: {dimension}")

        current_weight = self.BASELINE_WEIGHTS[dimension]
        gap = self.DIMENSION_GAPS.get(dimension, 0)

        proposal = {
            "type": "weight_decrease",
            "dimension": dimension,
            "current_weight": current_weight,
            "new_weight": new_weight,
            "change": new_weight - current_weight,
            "gap_score": gap,
            "rationale": f"Gap of +{gap:.2f} is lower than others. Decreasing weight slightly.",
        }

        return proposal

    def generate_improvement_sequence(self) -> List[Dict]:
        """
        Generate a sequence of improvement proposals to test.

        Strategy:
        1. Increase weights of top 3 dimensions (highest gaps)
        2. Decrease weights of bottom 2 dimensions (lowest gaps)
        3. Test one change at a time

        Returns:
            List of proposals in order to test
        """
        proposals = []

        # Top 3 dimensions by gap (increase weights)
        top_dims = sorted(self.DIMENSION_GAPS.items(), key=lambda x: x[1], reverse=True)[:3]
        for dim, gap in top_dims:
            current = self.BASELINE_WEIGHTS[dim]
            new_weight = min(current + 0.05, 1.0)  # Increase by 5%, cap at 1.0
            if new_weight > current:
                proposal = self.propose_weight_increase(dim, new_weight)
                proposals.append(proposal)

        # Bottom 2 dimensions by gap (decrease weights)
        bottom_dims = sorted(self.DIMENSION_GAPS.items(), key=lambda x: x[1])[:2]
        for dim, gap in bottom_dims:
            current = self.BASELINE_WEIGHTS[dim]
            new_weight = max(current - 0.03, 0.0)  # Decrease by 3%, floor at 0.0
            if new_weight < current:
                proposal = self.propose_weight_decrease(dim, new_weight)
                proposals.append(proposal)

        return proposals

    def apply_proposal_to_config(self, config: Dict, proposal: Dict) -> Dict:
        """
        Apply a proposal to a config dict.

        Args:
            config: Config dict (parsed from config.json)
            proposal: Proposal dict

        Returns:
            Updated config dict
        """
        config_copy = json.loads(json.dumps(config))  # Deep copy

        if proposal["type"] in ["weight_increase", "weight_decrease"]:
            dim = proposal["dimension"]
            new_weight = proposal["new_weight"]

            # Update evaluator_config.json weights
            if "evaluator_config" not in config_copy:
                config_copy["evaluator_config"] = {}

            config_copy["evaluator_config"][dim] = new_weight

        return config_copy

    def proposal_to_string(self, proposal: Dict) -> str:
        """
        Format proposal as readable string.

        Args:
            proposal: Proposal dict

        Returns:
            Formatted string
        """
        dim = proposal["dimension"]
        old = proposal["current_weight"]
        new = proposal["new_weight"]
        change = proposal["change"]
        gap = proposal["gap_score"]

        return (
            f"{dim:25} | {old:.2f} → {new:.2f} ({change:+.2f}) | "
            f"Gap: +{gap:.2f} | {proposal['rationale']}"
        )

    @staticmethod
    def suggestions_for_baseline() -> str:
        """Print suggestions based on baseline analysis."""
        gaps = AutoProposer.DIMENSION_GAPS
        weights = AutoProposer.BASELINE_WEIGHTS

        print("\nBased on per-dimension gap analysis:")
        print("=" * 80)
        print("\nTOP PREDICTORS (highest gap = best separates winners from losers):")

        sorted_dims = sorted(gaps.items(), key=lambda x: x[1], reverse=True)
        for i, (dim, gap) in enumerate(sorted_dims[:3], 1):
            weight = weights[dim]
            suggestion = "INCREASE" if weight < 0.20 else "REVIEW"
            print(f"{i}. {dim:25} Gap: +{gap:.2f}  Current weight: {weight:.0%}  → {suggestion}")

        print("\nLOWER PREDICTORS (consider decreasing slightly):")
        for i, (dim, gap) in enumerate(sorted_dims[-2:], 1):
            weight = weights[dim]
            print(f"{i}. {dim:25} Gap: +{gap:.2f}  Current weight: {weight:.0%}")

        print("=" * 80)
