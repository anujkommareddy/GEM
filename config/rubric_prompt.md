# GEM Transcendence Rubric v2.0
## Producer-Grounded Evaluation (No Prestige Bias)

You are evaluating TV pilots to identify shows with the potential to become **transcendent** — culturally defining shows like Breaking Bad, The Sopranos, The Office, Game of Thrones, I Love Lucy, The Simpsons, Seinfeld, The Wire, Fleabag.

**Core principle:** Transcendent shows work across ALL genres and formats. They are not defined by "literary prestige" but by their ability to capture culture, sustain viewership, generate conversation, and endure.

---

## The 5 Dimensions

### 1. Audience Appeal & Marketability (1-10)

**What it measures:** How broadly appealing and marketable is this show? What's the addressable audience size and passion?

**Strong signals (7-10):**
- Clear, multi-quadrant appeal (kids AND adults, or men AND women, or multiple age groups)
- Emotional promise that's immediately obvious ("this is funny," "this is thrilling," "this is emotional")
- Premise that people immediately GET and WANT
- Natural word-of-mouth hooks (something people will tell their friends about)
- Genre that has proven cultural staying power

**Weak signals (1-6):**
- Niche audience only (appeals to TV critics, not broad public)
- Unclear what genre/tone the show is
- Premise requires explanation or context
- Limited upside beyond initial curiosity
- Genre with declining viewership

**Examples:**
- Breaking Bad (7-8): Clear appeal to drama/thriller audiences; high-concept hook; male-skewing but multi-generational
- The Office (8-9): Universal appeal; everyone recognizes workplace; cringe humor + heart works for broad audience
- The Simpsons (9-10): Family sitcom; appeal to all ages; instantly recognizable
- Fleabag (7-8): Female-skewing; millennial appeal; but strong word-of-mouth
- The Wire (6-7): More niche (prestige drama); smaller addressable audience initially; grew through word-of-mouth

---

### 2. Conceptual Hook & Clarity (1-10)

**What it measures:** How instantly graspable is the central premise? Can you explain it in 2 sentences? Does it land in the pilot?

**Strong signals (7-10):**
- High-concept or immediately intriguing premise
- The hook emerges early in the pilot (not buried)
- Stakes and story engine are crystal clear by end of pilot
- Premise is simple enough for casual viewer to follow
- Hook answers: "Why should I care? Why now? What's at stake?"

**Weak signals (1-6):**
- Premise requires backstory or outside context to understand
- Hook arrives late or feels buried
- Unclear what the show is actually ABOUT
- Overly complex setup that confuses rather than hooks
- Premise sounds generic or familiar without a clear twist

**Examples:**
- Seinfeld (9-10): "Show about nothing" / observational comedy about daily life — instantly gettable
- Breaking Bad (9-10): High school teacher + cancer diagnosis + methamphetamine — hook is immediate and clear
- The Wire (5-6): Premise requires understanding of Baltimore institutions; complex; takes time to land
- Game of Thrones (8-9): Fantasy epic with political intrigue; familiar enough (medieval + magic) but clearly high-stakes
- The Office (9): Documentary sitcom about mundane workplace; instantly clear what the show is

---

### 3. Character Appeal & Long-Term Potential (1-10)

**What it measures:** Are the leads charismatic, memorable, and durable enough to sustain 5+ seasons?

**Strong signals (7-10):**
- Lead(s) have clear desires and contradictions (they want something but it conflicts with something else)
- Characters are visibly different from each other; easy to tell apart
- Relationships generate obvious conflict/comedy/drama engines that could sustain multiple seasons
- Characters feel like *people* with lives and stakes, not just plot devices
- Supporting cast is distinctive and memorable (not interchangeable)
- Clear hooks for multi-season character arcs

**Weak signals (1-6):**
- Flat or interchangeable leads
- Characters are defined purely by their role (cop, lawyer, teacher) not by personality/contradiction
- Limited relational dynamics; unclear what would sustain a season 2
- Leads feel generic or seen-before
- Supporting cast feels forgettable
- Low sequelability for character arcs

**Examples:**
- Breaking Bad (9-10): Walter White's contradiction (meek teacher / ruthless criminal) generates unlimited season potential; chemistry with Jesse; clear multi-season arcs
- The Office (9-10): Michael Scott's core contradiction (wants to be liked / makes terrible decisions); rich ensemble relationships; every character is distinctive
- Seinfeld (9): Four leads with complementary neuroses; relationships generate infinite comedy engines
- The Sopranos (9-10): Tony Soprano's contradiction (mobster / therapy patient / family man); characters with clear arcs
- Game of Thrones (8-9): Ensemble cast; complex relationships; clear character arcs across seasons

---

### 4. Creative Originality & Boldness (1-10)

**What it measures:** How fresh/novel is the voice, angle, or approach? Does it take risks?

**Strong signals (7-10):**
- Novel angle on familiar territory OR entirely fresh concept
- Stylistic or structural choices that feel confident and distinctive
- Willingness to take tonal or narrative risks
- Surprises that still feel earned and coherent
- Voice/perspective that stands out from similar shows

**Weak signals (1-6):**
- Derivative premise; feels like many shows that came before it
- Safe, by-the-book execution
- No distinctive voice or style
- Familiar beats with no reinvention or fresh angle
- Plays it safe rather than taking risks

**Examples:**
- Breaking Bad (8-9): Crime show, but from the perspective of a protagonist becoming a villain (rare at the time); bold structural choices; unique visual style
- The Office (8-9): Sitcom format, but documentary-style mockumentary was bold; cringe comedy was risky in 2005
- The Sopranos (9-10): Prestige drama with mob antihero; completely novel in 1999
- Fleabag (8-9): Comedy structure but with fourth-wall breaks and emotional depth; fresh approach to storytelling
- Game of Thrones (7-8): Adapts books, but scope/scale/willingness to kill characters was bold; high-production-value fantasy on TV was novel in 2011

---

### 5. Narrative Momentum & Engagement (1-10)

**What it measures:** Does the pilot move? Are stakes clear? Does it compel you to watch the next episode?

**Strong signals (7-10):**
- Rising stakes or clear inciting incident
- Pacing that feels propulsive (not slack or meandering)
- Meaningful act turns; clear escalation
- Ending leaves you wanting more (cliffhanger, reframing, or hook)
- No dead air; scenes earn their space
- Pilot feels complete yet opens multiple story doors

**Weak signals (1-6):**
- Slow, meandering pacing
- Unclear stakes or low urgency
- Flat middle; scenes that don't advance
- Ending feels conclusive or anti-climactic
- Pilot tries to do too much or too little
- No propulsion toward "next episode"

**Examples:**
- Breaking Bad (9-10): Inciting incident (cancer diagnosis) arrives fast; escalates through the pilot; ends with commitment to meth; compulsive
- Seinfeld (7-8): Observational premise doesn't need heavy plot, but each segment escalates; ends with closure but promise of more
- The Office (8-9): Documentary format allows pacing; cringe moments escalate; ends with reframing of Michael; want to see more
- The Wire (5-6): Slower burn; less immediate propulsion; relies on thematic interest more than plot momentum
- Game of Thrones (9-10): Multiple storylines, escalation, shocking moment at end; propulsive; leaves many hooks

---

## Output Format

Provide evaluation as JSON:

```json
{
  "script_id": "SCRIPT_ID",
  "audience_appeal_marketability": {
    "score": X,
    "reasoning": "..."
  },
  "conceptual_hook_clarity": {
    "score": X,
    "reasoning": "..."
  },
  "character_appeal_and_long_term_potential": {
    "score": X,
    "reasoning": "..."
  },
  "creative_originality_and_boldness": {
    "score": X,
    "reasoning": "..."
  },
  "narrative_momentum_engagement": {
    "score": X,
    "reasoning": "..."
  },
  "summary": "Brief assessment of transcendence potential. Could this become a show people still talk about in 10 years?"
}
```

---

## Scoring Philosophy

- **5 = Baseline:** Competent, well-made pilot that got produced for good reason. Solid execution but nothing memorable.
- **7-8 = High-potential:** Has real distinctive qualities; stands out from the crowd; multiple elements working well together.
- **9-10 = Transcendent signal:** Combination of elements that suggest this could define a generation. Novel, compelling, durable, and culturally resonant.

---

## Key Rules

1. **Score the PILOT, not the show it became.** You're evaluating based on what's on the page, not IMDb ratings or career hindsight.
2. **Ignore the label (winner/loser).** Score each script independently.
3. **Compare across ALL genres.** A sitcom can score as high as a drama. A sketch show can score as high as a serialized thriller. Use the same standards.
4. **Trust observable signals.** Don't overthink. If multiple dimensions align strongly, that's signal.
5. **Be honest about commercial appeal.** Some transcendent shows are niche (The Wire) but most transcendent shows are broadly appealing. Note the difference.

