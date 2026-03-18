# Screenplay Feature Extraction — Transcendence Signals

Before scoring, extract and analyze the following from the script. Focus on signals that distinguish potentially transcendent television from competent television. Every script you read here was produced — you are not filtering for "good enough." You are looking for markers of greatness.

## Core Extraction

### Voice & Authorship
1. **Writer's Voice**: Describe the writing style in 2-3 sentences. Is it distinctive? Could you identify this writer from a blind page?
2. **Point of View**: What is the script's point of view on its subject matter? Is there a perspective that feels personal and urgent, or is it neutral/conventional?
3. **Tonal Signature**: What is the specific emotional texture? Not just "dark comedy" — be precise. (e.g., "mordant humor masking genuine grief" or "sunlit nostalgia with an undercurrent of dread")
4. **Risk Level**: Does the script take any big swings — structural, tonal, or thematic — that a safer version wouldn't?

### Character Signals
1. **Protagonist Complexity**: Name the protagonist. What are their contradictions? What makes them UNLIKE any character you've seen before? If they feel familiar, say so.
2. **Character Introduction Quality**: How are the main characters introduced? Is the introduction economical and revealing, or generic?
3. **Subtext in Relationships**: Do characters say what they mean, or is there a gap between what's said and what's felt?
4. **Ensemble Distinctiveness**: Can you tell characters apart by voice alone?

### Thematic Layer
1. **Surface Story**: What happens in the pilot (plot)?
2. **Deeper Story**: What is the pilot actually ABOUT thematically? (If nothing, say "no discernible thematic layer.")
3. **Thematic Nuance**: Does the script present its themes with complexity, or does it have a thesis it's trying to prove?

### World & Premise
1. **Setting**: Where and when.
2. **World Specificity**: How lived-in and detailed does this world feel? Is it a real place or a TV version of a place?
3. **Premise Engine**: What is the source of renewable dramatic tension? Could this sustain 5 seasons or does it feel like a movie stretched thin?
4. **Genre**: Primary genre and any genre-mixing.

### Memorable Moments
1. **Best Line**: Quote the single best line of dialogue (or note if nothing stands out).
2. **Best Scene**: Briefly describe the strongest scene and why it works.
3. **Boldest Choice**: What is the single most unconventional choice in the script?

---

## Output Format

```json
{
  "script_id": "SCRIPT_ID",
  "logline": "...",
  "writers_voice_description": "...",
  "point_of_view": "...",
  "tonal_signature": "...",
  "risk_level": "low|medium|high|very_high",
  "protagonist": {
    "name": "...",
    "contradictions": "...",
    "novelty": "...",
  },
  "ensemble_voice_distinctiveness": "low|medium|high",
  "subtext_present": true/false,
  "surface_story": "...",
  "thematic_layer": "...",
  "thematic_nuance": "low|medium|high",
  "setting": "...",
  "world_specificity": "generic|moderate|vivid|immersive",
  "premise_sustainability": "limited|moderate|strong|exceptional",
  "genre": "...",
  "best_line": "...",
  "best_scene": "...",
  "boldest_choice": "...",
  "gut_reaction": "One sentence — what stayed with you after reading?",
  "extraction_confidence": 0.0-1.0
}
```

## Notes
- Be honest. If a script is competent but unremarkable, say so. "Solid procedural with no distinguishing features" is a valid extraction.
- If you feel genuine excitement about a script, note it. That signal matters.
- Focus on the WRITING, not what the show might become with great casting or directing.
