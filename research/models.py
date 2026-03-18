"""Core data models for the GEM research pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WinnerLabel(str, Enum):
    WINNER = "winner"
    LOSER = "loser"
    AMBIGUOUS = "ambiguous"


class LabelScheme(BaseModel):
    """A specific interpretation of winner/loser criteria."""

    name: str
    description: str
    mapping: dict[str, WinnerLabel]
    exclude_ambiguous: bool = False


class ShowEntry(BaseModel):
    """A single row from the labeled Google Sheet."""

    title: str
    raw_label: str
    episode_title: Optional[str] = None
    network: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[int] = None
    extra: dict[str, str] = Field(default_factory=dict)


class Script(BaseModel):
    """A parsed script file."""

    filename: str
    show_title: str
    episode_title: Optional[str] = None
    text: str
    word_count: int = 0
    source_path: str = ""


class LinkedRecord(BaseModel):
    """A show entry linked to its script(s)."""

    show: ShowEntry
    scripts: list[Script] = Field(default_factory=list)
    match_confidence: float = 1.0
    match_method: str = "exact"

    def resolved_label(self, scheme: LabelScheme) -> Optional[WinnerLabel]:
        raw = self.show.raw_label.strip().lower()
        return scheme.mapping.get(raw)


# ---------------------------------------------------------------------------
# Facet definitions (replaces old FactorDefinition)
# ---------------------------------------------------------------------------

class FacetDefinition(BaseModel):
    """Definition of a single analysis facet."""

    name: str
    description: str
    strong_signals: str
    weak_signals: str
    scoring_guidance: str
    false_positives: str
    score_range: tuple[int, int] = (1, 10)


# Backward compat alias
FactorDefinition = FacetDefinition


class FacetScore(BaseModel):
    """Score for a single facet on a single script."""

    facet_name: str
    score: float
    confidence: float = 1.0
    rationale: str = ""
    notes: str = ""


# Backward compat: old code references FactorScore with factor_name field
class FactorScore(BaseModel):
    """Legacy model — use FacetScore for new code."""

    factor_name: str
    score: float
    confidence: float = 1.0
    evidence: str = ""
    notes: str = ""


class ScriptAnalysis(BaseModel):
    """Full analysis result for one script."""

    show_title: str
    episode_title: Optional[str] = None
    script_filename: str
    facet_scores: list[FacetScore] = Field(default_factory=list)
    summary: str = ""
    analysis_version: str = "v2"
    prompt_version: str = "v2"
    provider: str = ""  # "openai" or "anthropic"
    model: str = ""     # e.g. "gpt-4o-mini", "claude-haiku-4-5-20251001"

    # Backward compat: accept old factor_scores field and convert
    factor_scores: list[FactorScore] = Field(default_factory=list)

    def all_scores_by_name(self) -> dict[str, float]:
        """Get all scores as {name: score} dict, merging both fields."""
        out = {}
        for s in self.facet_scores:
            out[s.facet_name] = s.score
        for s in self.factor_scores:
            out[s.factor_name] = s.score
        return out


class FactorComparison(BaseModel):
    """Comparison of a facet across winners vs losers."""

    factor_name: str
    label_scheme: str
    winner_mean: float
    winner_std: float
    loser_mean: float
    loser_std: float
    separation: float
    n_winners: int
    n_losers: int
    p_value: Optional[float] = None


class StabilityResult(BaseModel):
    """How stable a facet is across different label schemes."""

    factor_name: str
    schemes_tested: list[str]
    separations: dict[str, float]
    mean_separation: float
    std_separation: float
    stable: bool
    direction_consistent: bool


class PipelineReport(BaseModel):
    """Final report output."""

    factors_ranked: list[dict]
    stable_factors: list[str]
    unstable_factors: list[str]
    best_label_scheme: str
    scheme_comparisons: list[dict]
    recommendations: list[str]
