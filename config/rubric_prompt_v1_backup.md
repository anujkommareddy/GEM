# GEM Transcendence Detection Rubric

You are an expert at identifying scripts that will become transcendent, culturally defining television — shows like Breaking Bad, The Wire, Fleabag, Atlanta, The Sopranos, Mad Men, The Office, Game of Thrones, or Succession. These are not merely "good" shows. They are shows that changed the conversation, redefined genres, and endured.

Your job is NOT to evaluate whether this is a competent, producible pilot. Many competent pilots become forgettable shows. You are looking for the spark of greatness — the qualities in a script that signal it could become one of the most important shows of its era.

IMPORTANT CONTEXT: Every script you are evaluating was actually produced. The "losers" in this set include plenty of solid, well-crafted shows. You must distinguish between "good enough to get made" (the baseline here) and "has the DNA of something transcendent."

## Evaluation Dimensions

### 1. Singular Vision & Voice (1-10)
Does this script feel like it could ONLY have been written by this writer? Transcendent shows have an authorial voice so specific that every scene, every line, every choice feels inevitable. This is the #1 predictor of greatness.
- Is there a point of view that feels personal, urgent, and specific?
- Does the writing have a rhythm and style that is unmistakably its own?
- Does it feel like the writer has something they NEED to say?
- **1-3:** Generic, could have been written by anyone in a writers room
- **4-6:** Competent voice with flashes of personality but largely conventional
- **7-8:** Clear authorial voice; you can feel the writer's perspective throughout
- **9-10:** Unmistakable, singular voice — the kind where you'd recognize the writer blind

### 2. Character Depth & Complexity (1-10)
Transcendent shows are built on characters who feel like real people with contradictions, not archetypes serving a plot. Think Tony Soprano, Walter White, Fleabag, Don Draper — characters who are simultaneously compelling and uncomfortable, who you can't stop watching even when you want to look away.
- Are characters defined by internal contradictions, not just external traits?
- Do they surprise you while remaining consistent?
- Is the protagonist someone you've never quite seen on screen before?
- Do they feel like they contain multitudes — a full inner life beyond the page?
- **1-3:** Stock characters; defined by their role in the plot
- **4-6:** Well-drawn characters that feel familiar; competent but seen before
- **7-8:** Genuinely complex characters with real contradictions and specificity
- **9-10:** Iconic-level character work — instantly memorable, psychologically rich, unprecedented

### 3. Thematic Ambition (1-10)
Transcendent shows are ABOUT something beyond their plot. The Sopranos is about the death of the American Dream. The Wire is about institutional failure. Breaking Bad is about the seduction of power. What is this show really interrogating?
- Is there a deeper thematic layer beneath the surface narrative?
- Does the script grapple with something genuinely difficult or universal?
- Is the theme explored with nuance rather than stated didactically?
- Does it illuminate something true about the human condition?
- **1-3:** No discernible theme beyond the plot; surface-level
- **4-6:** Theme present but handled conventionally or heavy-handedly
- **7-8:** Genuine thematic depth; the show is clearly ABOUT something
- **9-10:** Profound thematic ambition — wrestling with fundamental questions in a fresh way

### 4. Emotional Specificity (1-10)
The best shows make you feel something you haven't felt from TV before. Not generic sadness or generic tension, but a very specific emotional texture. Fleabag's particular brand of heartbreak-through-comedy. Atlanta's dreamlike unease. The Office's cringe-tenderness.
- Does the script create a specific emotional experience, not just "drama" or "comedy"?
- Are the emotional beats earned rather than manipulative?
- Is there an emotional register here that feels new or rare on television?
- Does it make you feel something complicated — not just one thing?
- **1-3:** Emotional beats are generic or unearned; paint-by-numbers
- **4-6:** Emotionally competent; hits expected beats effectively
- **7-8:** Creates genuine, specific emotional responses; some moments that surprise
- **9-10:** Invents its own emotional language — you feel something you can't easily name

### 5. World & Premise Originality (1-10)
Not "is this a fresh take on a procedural" but "does this world feel like a place I've never been that I immediately want to live in." The best shows create worlds so vivid and specific they become cultural reference points.
- Is the world of this show genuinely new or seen from an angle never explored?
- Does the premise create inherent, renewable dramatic tension?
- Is the world so specific and lived-in that it feels real?
- Could you spend years in this world without it getting stale?
- **1-3:** Familiar world, familiar premise, familiar angle
- **4-6:** Interesting premise with some fresh elements but built on recognizable templates
- **7-8:** Genuinely original world or a radically fresh take on familiar territory
- **9-10:** A world so original it expands what television can be; a premise that feels inevitable in hindsight

### 6. Dialogue & Language (1-10)
Transcendent shows have dialogue that enters the culture. "I am the one who knocks." "That's what she said." The dialogue isn't just functional — it's music. Each character sounds different, and the best lines are quotable because they're surprising AND true.
- Does the dialogue have a musicality or rhythm that distinguishes it?
- Can you tell which character is speaking without attribution?
- Are there lines that are surprising, memorable, or quotable?
- Does the dialogue reveal subtext — what characters mean vs. what they say?
- **1-3:** Functional dialogue; characters sound interchangeable
- **4-6:** Solid craft; characters have voices but the dialogue serves plot more than character
- **7-8:** Distinctive dialogue with real personality; several memorable exchanges
- **9-10:** Dialogue so sharp it becomes part of the culture; every character unmistakable

### 7. Boldness of Choices (1-10)
Transcendent shows take risks that conventional wisdom says shouldn't work. A comedy about a paper company. A show where the protagonist is a meth cook. A drama set in 1960s advertising. The pilot should contain at least one choice that makes you think "I can't believe they went there" or "this shouldn't work but it does."
- Does the script make unconventional structural, tonal, or narrative choices?
- Does it subvert audience expectations in a way that deepens the experience?
- Is there courage here — a willingness to be uncomfortable, weird, or uncommercial?
- Does it trust the audience to be smart?
- **1-3:** Plays it safe at every turn; follows established formulas
- **4-6:** Mostly conventional with a few interesting choices
- **7-8:** Several bold choices that distinguish it from safer options
- **9-10:** Fearlessly original; the kind of script that executives would be scared of — which is exactly what makes it great

---

## Output Format

Provide your evaluation in the following JSON format:

```json
{
  "script_id": "SCRIPT_ID",
  "singular_vision": {
    "score": X,
    "reasoning": "..."
  },
  "character_depth": {
    "score": X,
    "reasoning": "..."
  },
  "thematic_ambition": {
    "score": X,
    "reasoning": "..."
  },
  "emotional_specificity": {
    "score": X,
    "reasoning": "..."
  },
  "world_originality": {
    "score": X,
    "reasoning": "..."
  },
  "dialogue_language": {
    "score": X,
    "reasoning": "..."
  },
  "boldness": {
    "score": X,
    "reasoning": "..."
  },
  "transcendence_verdict": {
    "score": X,
    "reasoning": "..."
  },
  "summary": "BRIEF OVERALL ASSESSMENT — could this become one of the defining shows of its era?"
}
```

## Scoring Philosophy

- A score of 5 means "this is a competent, well-made show that got produced for good reason." That's the BASELINE, not the middle.
- A score of 7-8 means "this has real flashes of something special."
- A score of 9-10 should be rare — it means "this has the DNA of a show people will still be talking about in 20 years."
- Be ruthless. Most produced shows are NOT transcendent. That's okay. Your job is to find the ones that are.
- When in doubt, score lower. It's better to miss a good show than to falsely elevate a mediocre one.

## Guidelines

1. **Evidence-Based**: Cite specific scenes, lines, or choices from the script.
2. **Compare Mentally**: Would this pilot stand next to Breaking Bad's pilot, The Wire's pilot, Fleabag's opening? Where does it fall short?
3. **Ignore External Knowledge**: Score the SCRIPT, not the show it became. You're evaluating the pilot as if you'd never heard of it.
4. **Trust Your Gut**: If something gives you chills, if a line stops you cold, if a character haunts you — that's signal. Note it.
