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
    # Maps raw sheet values to WinnerLabel
    mapping: dict[str, WinnerLabel]
    # If true, rows mapped to AMBIGUOUS are excluded from analysis
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


class FactorDefinition(BaseModel):
    """Definition of a single analysis factor."""

    name: str
    description: str
    why_it_matters: str
    script_evidence: str
    false_positives: str
    score_range: tuple[int, int] = (1, 10)


class FactorScore(BaseModel):
    """Score for a single factor on a single script."""

    factor_name: str
    score: int
    confidence: float = 1.0
    evidence: str = ""
    notes: str = ""


class ScriptAnalysis(BaseModel):
    """Full analysis result for one script."""

    show_title: str
    episode_title: Optional[str] = None
    script_filename: str
    factor_scores: list[FactorScore] = Field(default_factory=list)
    analysis_version: str = "v1"
    prompt_version: str = "v1"


class FactorComparison(BaseModel):
    """Comparison of a factor across winners vs losers."""

    factor_name: str
    label_scheme: str
    winner_mean: float
    winner_std: float
    loser_mean: float
    loser_std: float
    separation: float  # effect size (Cohen's d or similar)
    n_winners: int
    n_losers: int
    p_value: Optional[float] = None


class StabilityResult(BaseModel):
    """How stable a factor is across different label schemes."""

    factor_name: str
    schemes_tested: list[str]
    separations: dict[str, float]  # scheme_name -> separation
    mean_separation: float
    std_separation: float
    stable: bool  # True if consistently separates winners/losers
    direction_consistent: bool  # True if always same direction


class PipelineReport(BaseModel):
    """Final report output."""

    factors_ranked: list[dict]  # sorted by usefulness
    stable_factors: list[str]
    unstable_factors: list[str]
    best_label_scheme: str
    scheme_comparisons: list[dict]
    recommendations: list[str]
