"""
Intelligently propose weight configurations for testing.
"""
import json
import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class WeightProposal:
    """A proposed weight configuration"""
    proposal_id: int
    name: str
    weights: Dict[str, float]
    rationale: str


class FacetProposer:
    """Generate intelligent weight proposals based on facet analysis"""

    # Current best-known baseline (from config)
    BASELINE_WEIGHTS = {
        "singular_vision": 0.25,
        "character_depth": 0.17,
        "thematic_ambition": 0.15,
        "emotional_specificity": 0.15,
        "world_originality": 0.10,
        "dialogue_language": 0.07,
        "boldness": 0.05,
    }

    def __init__(self, facet_metrics: Dict[str, Dict]):
        """
        facet_metrics: dict of {facet_name: {winner_avg, loser_avg, gap, ...}}
        """
        self.facet_metrics = facet_metrics
        self.facets = sorted(facet_metrics.keys())
        self.proposals = []

    def generate_proposals(self) -> List[WeightProposal]:
        """Generate 10+ intelligent proposals"""
        self.proposals = []
        proposal_id = 0

        # P0: Baseline (control)
        self.proposals.append(WeightProposal(
            proposal_id=proposal_id,
            name="Baseline (v1.0)",
            weights=self.BASELINE_WEIGHTS.copy(),
            rationale="Current configuration from best_config_v1"
        ))
        proposal_id += 1

        # P1: Gap-weighted (increase high-gap, decrease low-gap)
        gap_weights = self._generate_gap_weighted()
        self.proposals.append(WeightProposal(
            proposal_id=proposal_id,
            name="Gap-weighted (high-gap gets more weight)",
            weights=gap_weights,
            rationale="Allocate weight proportional to winner-loser gap"
        ))
        proposal_id += 1

        # P2: Uniform (equal weight)
        uniform_weights = {f: 1.0/len(self.facets) for f in self.facets}
        self.proposals.append(WeightProposal(
            proposal_id=proposal_id,
            name="Uniform weights",
            weights=uniform_weights,
            rationale="Equal contribution from all facets"
        ))
        proposal_id += 1

        # P3: Sparse (top 3 facets only)
        sparse_weights = self._generate_sparse(top_n=3)
        self.proposals.append(WeightProposal(
            proposal_id=proposal_id,
            name="Sparse (top 3 facets)",
            weights=sparse_weights,
            rationale="Focus on 3 highest-gap facets"
        ))
        proposal_id += 1

        # P4: Sparse (top 4 facets)
        sparse4_weights = self._generate_sparse(top_n=4)
        self.proposals.append(WeightProposal(
            proposal_id=proposal_id,
            name="Sparse (top 4 facets)",
            weights=sparse4_weights,
            rationale="Focus on 4 highest-gap facets"
        ))
        proposal_id += 1

        # P5: Boost boldness + singular_vision
        boost_weights = self.BASELINE_WEIGHTS.copy()
        boost_weights["boldness"] *= 2.0
        boost_weights["singular_vision"] *= 1.2
        # Renormalize
        total = sum(boost_weights.values())
        boost_weights = {f: w/total for f, w in boost_weights.items()}
        self.proposals.append(WeightProposal(
            proposal_id=proposal_id,
            name="Boost boldness + singular_vision",
            weights=boost_weights,
            rationale="Give more weight to daring/distinctive facets"
        ))
        proposal_id += 1

        # P6: Penalize low-gap facets
        penalize_weights = self.BASELINE_WEIGHTS.copy()
        for facet in self.facets:
            gap_percentile = self.facet_metrics[facet].get("gap_percentile", 50)
            if gap_percentile < 40:  # Bottom 40%
                penalize_weights[facet] *= 0.3
        # Renormalize
        total = sum(penalize_weights.values())
        penalize_weights = {f: w/total for f, w in penalize_weights.items()}
        self.proposals.append(WeightProposal(
            proposal_id=proposal_id,
            name="Penalize low-gap facets",
            weights=penalize_weights,
            rationale="Reduce weight on facets with weak winner-loser separation"
        ))
        proposal_id += 1

        # P7: Exponential gap-weighting
        exp_gap_weights = self._generate_exponential_gap_weighted()
        self.proposals.append(WeightProposal(
            proposal_id=proposal_id,
            name="Exponential gap-weighting",
            weights=exp_gap_weights,
            rationale="Exponentially favor high-gap facets"
        ))
        proposal_id += 1

        # P8: Quadratic scaling
        quad_weights = self._generate_quadratic_scaled()
        self.proposals.append(WeightProposal(
            proposal_id=proposal_id,
            name="Quadratic gap scaling",
            weights=quad_weights,
            rationale="Gap-squared weighting"
        ))
        proposal_id += 1

        # P9: Inverse std dev (favor consistent facets)
        inv_std_weights = self._generate_inverse_stddev()
        self.proposals.append(WeightProposal(
            proposal_id=proposal_id,
            name="Inverse std dev (favor consistency)",
            weights=inv_std_weights,
            rationale="Weight facets by 1/stddev (favor low-noise facets)"
        ))
        proposal_id += 1

        # P10: Two-tier (vision/character high, others low)
        two_tier = {
            "singular_vision": 0.30,
            "character_depth": 0.30,
            "thematic_ambition": 0.10,
            "emotional_specificity": 0.10,
            "world_originality": 0.10,
            "dialogue_language": 0.05,
            "boldness": 0.05,
        }
        self.proposals.append(WeightProposal(
            proposal_id=proposal_id,
            name="Two-tier (vision/character dominant)",
            weights=two_tier,
            rationale="Core characterization + vision drive transcendence"
        ))
        proposal_id += 1

        return self.proposals

    def _generate_gap_weighted(self) -> Dict[str, float]:
        """Weight by gap (winner_avg - loser_avg)"""
        gaps = {f: self.facet_metrics[f]["gap"] for f in self.facets}
        min_gap = min(gaps.values())
        # Shift to positive
        shifted = {f: gaps[f] - min_gap + 0.1 for f in self.facets}
        total = sum(shifted.values())
        return {f: shifted[f] / total for f in self.facets}

    def _generate_sparse(self, top_n: int = 3) -> Dict[str, float]:
        """Only weight top N facets by gap"""
        gaps = {f: self.facet_metrics[f]["gap"] for f in self.facets}
        sorted_facets = sorted(gaps.keys(), key=lambda f: gaps[f], reverse=True)
        weights = {}
        for f in self.facets:
            if f in sorted_facets[:top_n]:
                weights[f] = 1.0 / top_n
            else:
                weights[f] = 0.0
        return weights

    def _generate_exponential_gap_weighted(self) -> Dict[str, float]:
        """Exponential gap weighting"""
        gaps = {f: self.facet_metrics[f]["gap"] for f in self.facets}
        min_gap = min(gaps.values())
        shifted = {f: gaps[f] - min_gap + 0.1 for f in self.facets}
        exp_weights = {f: np.exp(shifted[f]) for f in self.facets}
        total = sum(exp_weights.values())
        return {f: exp_weights[f] / total for f in self.facets}

    def _generate_quadratic_scaled(self) -> Dict[str, float]:
        """Gap-squared weighting"""
        gaps = {f: self.facet_metrics[f]["gap"] for f in self.facets}
        min_gap = min(gaps.values())
        shifted = {f: gaps[f] - min_gap + 0.1 for f in self.facets}
        quad_weights = {f: shifted[f] ** 2 for f in self.facets}
        total = sum(quad_weights.values())
        return {f: quad_weights[f] / total for f in self.facets}

    def _generate_inverse_stddev(self) -> Dict[str, float]:
        """Weight by 1/stddev (favor low-noise facets)"""
        std_devs = {f: self.facet_metrics[f].get("std_dev", 1.0) for f in self.facets}
        inv_weights = {f: 1.0 / (std_devs[f] + 0.01) for f in self.facets}
        total = sum(inv_weights.values())
        return {f: inv_weights[f] / total for f in self.facets}

    def print_proposals(self):
        """Print all proposals"""
        print("\n" + "="*100)
        print("WEIGHT PROPOSALS FOR TESTING")
        print("="*100)
        for prop in self.proposals:
            print(f"\nP{prop.proposal_id}: {prop.name}")
            print(f"  Rationale: {prop.rationale}")
            print(f"  Weights: {json.dumps(prop.weights, indent=14)}")
        print("="*100 + "\n")


if __name__ == "__main__":
    # Load facet analysis
    with open("./autoresearch/data/results/facet_analysis.json") as f:
        metrics = json.load(f)

    proposer = FacetProposer(metrics)
    proposals = proposer.generate_proposals()
    proposer.print_proposals()

    # Save proposals for auto_facet_research to use
    proposals_data = [
        {
            "proposal_id": p.proposal_id,
            "name": p.name,
            "weights": p.weights,
            "rationale": p.rationale
        }
        for p in proposals
    ]
    with open("./autoresearch/data/results/facet_proposals.json", "w") as f:
        json.dump(proposals_data, f, indent=2)
    print("Saved proposals to facet_proposals.json")
