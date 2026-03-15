"""Phase 3: Candidate factor framework.

Defines the factors used to analyze scripts, with clear definitions
and rationale for each.
"""

from __future__ import annotations

from models import FactorDefinition


def get_default_factors() -> list[FactorDefinition]:
    """Return the initial set of candidate factors for script analysis."""
    return [
        FactorDefinition(
            name="premise_strength",
            description="How compelling and clear the central premise is. Can you pitch it in one sentence and make someone lean in?",
            why_it_matters="A strong premise is the single biggest driver of initial audience interest. It determines whether anyone gives the show a chance.",
            script_evidence="Look at the logline implied by the pilot. Is the central conflict/situation immediately graspable? Does it suggest ongoing story potential? Does page 1-5 set up a clear 'what if' that creates curiosity?",
            false_positives="High-concept premises can score well here but fail in execution. A great premise poorly executed still fails. Also, some prestige shows have quiet premises that grow on audiences — this factor may undervalue slow burns.",
        ),
        FactorDefinition(
            name="hook_clarity",
            description="How quickly and effectively the script grabs attention in the opening pages and establishes stakes.",
            why_it_matters="Audiences decide in minutes whether to keep watching. A clear hook reduces drop-off and makes marketing easier.",
            script_evidence="First 5-10 pages: Is there a question planted? A mystery? A moment of tension or surprise? Does the reader feel compelled to keep going? Is there a 'promise' of what the show will deliver?",
            false_positives="Shock-value openings (cold open deaths, explosions) can score high but don't indicate lasting quality. Some great shows have deliberately slow openings that reward patience.",
        ),
        FactorDefinition(
            name="character_magnetism",
            description="How compelling, specific, and watchable the central character(s) are. Would you follow this person for 100 episodes?",
            why_it_matters="Character attachment is the primary driver of long-term viewing and word-of-mouth. Great characters can carry weak plots; weak characters sink great premises.",
            script_evidence="Does the protagonist have a clear want, a clear flaw, and a distinctive voice? Are their choices surprising but believable? Do they have moments that reveal depth? Is their dialogue specific to them (not interchangeable)?",
            false_positives="Likability is not magnetism — antiheroes and difficult characters can be highly magnetic. Also, ensemble shows may not have one standout but succeed through chemistry.",
        ),
        FactorDefinition(
            name="series_engine",
            description="How sustainable and repeatable the show's core dramatic mechanism is. What generates new stories week after week?",
            why_it_matters="TV needs to sustain across seasons. A clear engine (cases, missions, relationship dynamics, institutional conflict) is essential for longevity and reduces the risk of running out of story.",
            script_evidence="Can you identify what generates new episodes? Is there both an episodic engine (case-of-the-week, problem-of-the-week) and a serialized engine (character arcs, mysteries)? Does the pilot demonstrate both?",
            false_positives="A strong engine doesn't guarantee quality — procedurals have great engines but can feel formulaic. Limited series intentionally lack engines. Some breakout shows succeed by subverting expected engines.",
        ),
        FactorDefinition(
            name="originality",
            description="How fresh the show feels relative to what's currently on air. Does it offer a perspective, world, or format that feels new?",
            why_it_matters="Originality drives cultural conversation and press coverage. In a crowded landscape, being different is a competitive advantage. But it's a double-edged sword — too original can mean too niche.",
            script_evidence="Compare the premise, setting, character types, and tone to current/recent shows. Is there a meaningful twist on a familiar genre? A new angle on a known world? An underrepresented perspective?",
            false_positives="Originality alone doesn't predict success — familiar formats with great execution often outperform. What reads as 'original' to critics may read as 'confusing' to general audiences.",
        ),
        FactorDefinition(
            name="emotional_pull",
            description="How effectively the script generates genuine emotional response — laughter, tears, tension, joy, dread.",
            why_it_matters="Emotional engagement is what turns casual viewers into passionate fans. Shows that make people feel strongly get recommended, rewatched, and discussed.",
            script_evidence="Are there moments in the pilot that produce a genuine emotional response? Does the script earn its emotional beats (vs. manipulating for unearned sentiment)? Is there variety in emotional register?",
            false_positives="Sentimentality can mimic emotional pull without substance. Trauma dumps and 'very special episode' beats can feel powerful on paper but hollow in practice. Comedy scripts may read flat but play brilliantly.",
        ),
        FactorDefinition(
            name="world_distinctiveness",
            description="How vivid, specific, and immersive the world of the show is. Does it feel like a place you haven't seen before?",
            why_it_matters="Distinctive worlds drive visual identity, social media buzz, and franchise potential. They give audiences a 'place to visit' and expand the creative sandbox for writers.",
            script_evidence="Is the setting described with specific, evocative detail? Are there rules, customs, or textures unique to this world? Does the world feel lived-in rather than generic? Do characters interact with the world in ways that reveal it?",
            false_positives="World-building can be a trap — too much detail slows the story. Some breakout shows are set in generic locations (apartments, offices) and succeed through character. Exotic settings don't save bad stories.",
        ),
        FactorDefinition(
            name="scene_propulsion",
            description="How effectively each scene creates momentum toward the next. Does every scene end with a reason to keep reading/watching?",
            why_it_matters="Propulsion is what keeps viewers from picking up their phones. It's the mechanical backbone of binge-watching and strong same-day ratings.",
            script_evidence="Do scenes end on questions, revelations, or shifts? Is there a clear cause-and-effect chain? Does the script avoid dead spots where nothing is at stake? Does pacing vary effectively?",
            false_positives="Relentless pacing can be exhausting and feel hollow. Some great shows use deliberate stillness as a strength. Cliffhanger-dependent shows can score high here but burn out audiences.",
        ),
        FactorDefinition(
            name="dialogue_sharpness",
            description="How distinctive, quotable, and character-specific the dialogue is. Does it pop off the page?",
            why_it_matters="Great dialogue drives social media engagement, quotability, and critical praise. It's the most immediately visible signal of writing quality.",
            script_evidence="Can you identify the speaker from dialogue alone? Are there lines that surprise? Is subtext present? Does the dialogue serve multiple functions (character, plot, theme) simultaneously?",
            false_positives="Witty dialogue can mask thin characters and weak plotting. Quotable one-liners don't equal good drama. Genre shows (sci-fi, fantasy) may have functional dialogue that serves world-building instead.",
        ),
        FactorDefinition(
            name="commercial_clarity",
            description="How easy the show is to market. Can a network exec explain what it is in 15 seconds? Does the trailer cut itself?",
            why_it_matters="Even great shows fail if audiences don't know what they're getting. Clear commercial identity helps marketing, scheduling, and audience targeting.",
            script_evidence="Is the genre clear? Is there a visual hook? Can you imagine the poster/trailer? Does the show have a clear comp (it's X meets Y)? Is the target audience identifiable?",
            false_positives="Maximum commercial clarity often means maximum derivative risk. The most commercially clear shows may be the least original. Some breakout shows (Lost, Fleabag) defied easy categorization.",
        ),
        FactorDefinition(
            name="derivative_risk",
            description="How much the show feels like a copy or recombination of existing hits. Higher score = MORE derivative (this is a risk factor, not a strength).",
            why_it_matters="Derivative shows face uphill battles for press attention, critical acclaim, and passionate fandom. They're the first to be cancelled when ratings dip.",
            script_evidence="Can you name 3+ existing shows this closely resembles? Are the character archetypes stock types without meaningful twists? Is the premise a known formula (cop show, medical drama, family sitcom) without a differentiating angle?",
            false_positives="Some derivative shows succeed massively by executing a proven formula extremely well (NCIS, Law & Order spinoffs). Genre conventions aren't the same as being derivative. Familiar can be comforting.",
        ),
        FactorDefinition(
            name="word_of_mouth_potential",
            description="How likely viewers are to actively recommend this to friends. Does it create evangelists?",
            why_it_matters="In the streaming era, word-of-mouth is the dominant growth mechanism. Shows that generate passionate advocacy grow; shows that are 'fine' disappear.",
            script_evidence="Is there a 'you have to watch this' moment? Does the show have a unique quality that makes people want to explain it? Is there a surprise, twist, or emotional peak that demands sharing? Does it create in-group knowledge?",
            false_positives="Shock value and plot twists generate short-term buzz but not lasting advocacy. Water-cooler moments don't equal sustained word-of-mouth. Some quiet shows build devoted followings slowly without viral moments.",
        ),
    ]


def get_factor_names() -> list[str]:
    """Return just the names of all default factors."""
    return [f.name for f in get_default_factors()]


def get_factor_by_name(name: str) -> FactorDefinition:
    """Get a specific factor definition by name."""
    for f in get_default_factors():
        if f.name == name:
            return f
    raise ValueError(f"Unknown factor: {name}")


def factors_as_prompt_context() -> str:
    """Format all factors into a string suitable for inclusion in an analysis prompt."""
    lines = []
    for f in get_default_factors():
        lines.append(f"### {f.name}")
        lines.append(f"**Definition:** {f.description}")
        lines.append(f"**Why it matters:** {f.why_it_matters}")
        lines.append(f"**What to look for:** {f.script_evidence}")
        lines.append(f"**Watch out for:** {f.false_positives}")
        lines.append(f"**Score range:** {f.score_range[0]}-{f.score_range[1]}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print("GEM Research — Candidate Factors\n")
    print(f"Total factors: {len(get_default_factors())}\n")
    for f in get_default_factors():
        print(f"  {f.name}")
        print(f"    {f.description[:80]}...")
        print()
