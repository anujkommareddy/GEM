"""Facet framework for script analysis.

Defines the 5 core facets used to evaluate TV pilot scripts.
"""

from __future__ import annotations

from models import FacetDefinition


def get_default_facets() -> list[FacetDefinition]:
    """Return the 5 core facets for script analysis."""
    return [
        FacetDefinition(
            name="audience_appeal_marketability",
            description="Measures likely commercial reach and broad audience interest.",
            strong_signals="Multi-quadrant premise; clear emotional promise; accessible genre; evident rewatch/word-of-mouth hooks.",
            weak_signals="Niche or confusing premise; unclear audience; inaccessible tone; limited upside beyond a narrow cohort.",
            scoring_guidance="High scores (8-10): premise clearly appeals across demographics with built-in marketing hooks. Mid scores (5-7): decent appeal but limited to a specific audience segment. Low scores (1-4): premise is inaccessible, confusing, or appeals to a very narrow niche.",
            false_positives="Broad appeal doesn't mean bland — distinctive shows can be highly marketable. Don't conflate 'safe' with 'marketable'. Some niche premises have outsized cultural impact.",
        ),
        FacetDefinition(
            name="conceptual_hook_clarity",
            description="Measures how instantly graspable and compelling the central concept is.",
            strong_signals="High-concept elevator pitch; premise emerges early; stakes and engine are crisply expressed in the pilot.",
            weak_signals="Murky premise; unclear engine; requires outside context; hook buried late or never lands.",
            scoring_guidance="High scores (8-10): you can pitch the show in one sentence and it immediately generates curiosity. Mid scores (5-7): concept is clear but doesn't compel on its own. Low scores (1-4): after reading the pilot you still can't articulate what the show IS.",
            false_positives="High-concept doesn't mean simple — layered concepts can still be instantly graspable. Don't penalize complexity if the hook itself is clear. Some prestige shows have quiet hooks that are clear but not flashy.",
        ),
        FacetDefinition(
            name="character_appeal_and_long_term_potential",
            description="Measures charisma, memorability, and capacity for multi-season arcs.",
            strong_signals="Distinctive leads with clear desires, contradictions, and conflict generators; relationships suggest many episode engines.",
            weak_signals="Flat or interchangeable characters; unclear drives; limited relationship dynamism; low sequelability.",
            scoring_guidance="High scores (8-10): characters you'd follow for 100 episodes — specific voices, active choices, rich contradictions. Mid scores (5-7): functional characters that serve the plot but don't transcend it. Low scores (1-4): generic archetypes with no distinctive voice or inner life.",
            false_positives="Likability is not the same as appeal — antiheroes and difficult characters can score high here. Ensemble shows may score through chemistry rather than one standout lead. Don't conflate character complexity with character appeal.",
        ),
        FacetDefinition(
            name="creative_originality_and_boldness",
            description="Measures freshness of voice/structure and willingness to take risks.",
            strong_signals="Novel angle, voice, or structure that still reads coherent; surprising yet motivated choices; confident stylistic identity.",
            weak_signals="Derivative beats; generic voice; safe choices that feel overfamiliar without reinvention.",
            scoring_guidance="High scores (8-10): you haven't seen this show before — the voice, structure, or angle is genuinely fresh while remaining coherent. Mid scores (5-7): competent execution of familiar territory with some distinguishing choices. Low scores (1-4): feels like a recombination of existing hits with nothing new to say.",
            false_positives="Originality alone doesn't predict success. Weirdness for its own sake isn't boldness. Familiar frameworks executed with genuine craft can still score mid-range. Don't penalize genre conventions if the execution brings genuine voice.",
        ),
        FacetDefinition(
            name="narrative_momentum_engagement",
            description="Measures pacing, escalation, and compulsion to continue.",
            strong_signals="Rising stakes and reversals; clear act turns; ending meaningfully rehooks or reframes; minimal dead air.",
            weak_signals="Meandering progression; static stakes; inert middle; ending lacks propulsion.",
            scoring_guidance="High scores (8-10): you couldn't stop reading — each scene drives to the next, stakes escalate, and the ending demands you watch episode two. Mid scores (5-7): generally moves forward but has flat stretches or predictable beats. Low scores (1-4): no sense of urgency, stakes don't build, ending doesn't compel continuation.",
            false_positives="Relentless pacing can be exhausting and hollow. Deliberate stillness can be a strength in the right hands. Don't confuse cliffhangers with genuine momentum — cheap hooks burn out fast. Some excellent pilots use a slow build that pays off in a final-act reframe.",
        ),
    ]


def get_facet_names() -> list[str]:
    """Return just the names of all default facets."""
    return [f.name for f in get_default_facets()]


def get_facet_by_name(name: str) -> FacetDefinition:
    """Get a specific facet definition by name."""
    for f in get_default_facets():
        if f.name == name:
            return f
    raise ValueError(f"Unknown facet: {name}")


def facets_as_prompt_context() -> str:
    """Format all facets into a string suitable for inclusion in an analysis prompt."""
    lines = []
    for f in get_default_facets():
        lines.append(f"### {f.name}")
        lines.append(f"**Definition:** {f.description}")
        lines.append(f"**Strong signals:** {f.strong_signals}")
        lines.append(f"**Weak signals:** {f.weak_signals}")
        lines.append(f"**Scoring guidance:** {f.scoring_guidance}")
        lines.append(f"**Watch out for:** {f.false_positives}")
        lines.append(f"**Score range:** {f.score_range[0]}-{f.score_range[1]}")
        lines.append("")
    return "\n".join(lines)


# Keep backward-compat aliases for any code that imports old names
get_default_factors = get_default_facets
get_factor_names = get_facet_names
factors_as_prompt_context = facets_as_prompt_context


if __name__ == "__main__":
    print("GEM Research — Core Facets\n")
    print(f"Total facets: {len(get_default_facets())}\n")
    for f in get_default_facets():
        print(f"  {f.name}")
        print(f"    {f.description}")
        print()
