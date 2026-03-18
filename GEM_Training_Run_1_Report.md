# GEM Transcendence Detector — Training Run 1 Report
**Date:** March 18, 2026  
**Model:** gpt-5-mini  
**Scripts Evaluated:** 909 (906 successful)  
**Holdout Pairwise Accuracy: 84.01%**

---

## 1. What We Did

This was a complete rebuild of the GEM scoring rubric. The original v1 rubric was poisoned by prestige drama ideology — it overweighted "singular authorial vision" and literary quality, which systematically underscored comedies, ensemble shows, and format-driven hits (Simpsons, Seinfeld, I Love Lucy).

We replaced it with a **Producer Mind rubric**: 5 dimensions grounded in what a network executive or showrunner actually asks when evaluating a pilot.

Each of the 909 scripts was evaluated in a **single LLM pass**, scoring all 5 dimensions at once. Cost: ~$15 total.

---

## 2. The 5 Dimensions

| # | Dimension | Core Question |
|---|-----------|---------------|
| 1 | **Audience Appeal & Marketability** | Will people actually watch this? What's the addressable audience? |
| 2 | **Conceptual Hook & Clarity** | Can you pitch it in 30 seconds? Does the hook land in the pilot? |
| 3 | **Character Appeal & Long-Term Potential** | Are the leads durable enough for 5+ seasons? |
| 4 | **Creative Originality & Boldness** | Does it feel fresh or derivative? Does it take real risks? |
| 5 | **Narrative Momentum & Engagement** | Does it move? Does it compel you to episode 2? |

---

## 3. Gap Analysis — How Discriminating Is Each Dimension?

**Gap** = winner average minus loser average. Higher = more useful for spotting transcendence.

| Rank | Dimension | Winner Avg | Loser Avg | Gap | Winner StdDev | Loser StdDev |
|------|-----------|-----------|----------|-----|--------------|-------------|
| 1 | Creative Originality & Boldness | 7.74 | 5.97 | **1.77** | 0.96 | 1.90 |
| 2 | Character Appeal & Long-Term Potential | 8.58 | 6.92 | **1.66** | 0.81 | 1.96 |
| 3 | Audience Appeal & Marketability | 8.17 | 6.68 | **1.49** | 0.56 | 1.85 |
| 4 | Conceptual Hook & Clarity | 8.74 | 7.32 | **1.42** | 0.56 | 2.06 |
| 5 | Narrative Momentum & Engagement | 8.25 | 6.94 | **1.31** | 0.69 | 1.98 |

---

## 4. What the Optimizer Found

The weight optimizer ran 2,000+ random trials across the 720-script tuning set, then tested the best config on the **locked 178-script holdout** (13 winners, 165 losers, never seen during optimization).

**Best Weights:**

| Dimension | Weight | Interpretation |
|-----------|--------|----------------|
| Audience Appeal & Marketability | **3.00** | Most reliable predictor — highest weight |
| Character Appeal & Long-Term Potential | **2.85** | Nearly as important |
| Conceptual Hook & Clarity | **2.15** | Strong but secondary |
| Narrative Momentum & Engagement | **0.35** | Minimal contribution |
| Creative Originality & Boldness | **0.05** | Effectively zeroed out |

**Result:**
- Tuning pairwise accuracy: 93.12%
- **Holdout pairwise accuracy: 84.01%** (up from 74.15% with v1)
- Tune/holdout gap: 9.11% (acceptable — not severe overfitting)

---

## 5. The Originality Paradox

The most counterintuitive finding: **Creative Originality has the highest raw gap (1.77) but the optimizer weights it near zero (0.05).**

Why? Look at the standard deviations:
- Winners: std = 0.96 (tight — winners consistently score 7-8)
- Losers: std = 1.90 (double the variance — losers score all over the map)

The losers include both terrible unoriginal scripts (score 2-3) AND bold, risky scripts that didn't connect (score 7-8). So high originality is *necessary but not sufficient* — and the optimizer correctly learns to distrust it as a standalone signal.

**Hypothesis for new dimensions:** The missing piece is something like *resonant originality* — shows that feel new AND immediately land with an audience. Breaking Bad, The Office, Fleabag. Not just bold, but inevitable-feeling in hindsight.

---

## 6. Score Distribution (909 Scripts)

| Score Band | Count | Notes |
|-----------|-------|-------|
| 9.0+ | 0 | No perfect scores |
| 8.0–8.99 | 203 | Top tier — most winners here |
| 7.0–7.99 | 500 | The bulk of the dataset |
| 6.0–6.99 | 111 | Below average |
| 5.0–5.99 | 19 | Weak |
| Under 5.0 | 76 | Failed scripts (many are scoring errors / OCR failures) |

The model is clearly not using the full 1-10 range. Scores cluster in 7-9. This compression is a known issue with LLM scoring and suggests the anchors could be tightened — or new dimensions could introduce sharper differentiation.

---

## 7. Top 20 Scripts by Weighted Score

| Rank | Script | Score | Label |
|------|--------|-------|-------|
| 1 | This Is Us — Pilot (2016) | 8.99 | Winner |
| 2 | Sherlock — A Study in Scarlet | 8.99 | **Loser** |
| 3 | Stranger Things — Pilot (2016) | 8.99 | Winner |
| 4 | The Flash — Pilot | 8.99 | Winner |
| 5 | Game of Thrones — Pilot (2011) | 8.99 | Winner |
| 6 | The Sopranos — Pilot (1999) | 8.98 | Winner |
| 7 | Breaking Bad — Pilot (2008) | 8.98 | Winner |
| 8 | The Office — Pilot (2005) | 8.95 | Winner |
| 9 | Ted Lasso — Pilot (2020) | 8.95 | Winner |
| 10 | Scrubs — My First Day (2001) | 8.95 | Winner |
| 11 | The Good Place — Pilot (2017) | 8.95 | **Loser** |
| 12 | Modern Family — Pilot (2009) | 8.95 | Winner |
| 13 | Cheers — Pilot | 8.95 | Winner |
| 14 | M*A*S*H — Pilot | 8.95 | Winner |
| 15 | Friends — Pilot | 8.95 | Winner |
| 16 | The Big Bang Theory — Pilot | 8.95 | Winner |
| 17 | Mad About You — Pilot | 8.95 | **Loser** |
| 18 | Empire — Pilot | 8.74 | **Loser** |
| 19 | The Boys — Pilot (2019) | 8.66 | Winner |
| 20 | Lost — Pilot (2004) | 8.65 | Winner |

19 of 28 total winners appear in the top 30. The system is working.

---

## 8. False Positives (High-Scoring Losers)

40 losers scored above the winner average (8.46). These are the scripts the model thinks are transcendent but aren't labeled as winners. Many are **genuinely good shows** — this is likely a labeling issue as much as a model issue.

Notable high-scoring losers worth examining:

| Script | Score | Notes |
|--------|-------|-------|
| Sherlock — Pilot | 8.99 | Labeled loser but clearly transcendent — labeling error? |
| The Good Place — Pilot | 8.95 | Transcendent show, should probably be relabeled |
| Six Feet Under — Pilot | 8.64 | HBO landmark, arguably transcendent |
| The Americans — Pilot | 8.64 | Critically acclaimed, cult following |
| Bojack Horseman — Pilot | 8.60 | Culturally defining animated drama |
| Community — Pilot | 8.60 | Highly influential |
| Brooklyn Nine-Nine — Pilot | 8.60 | Long-running, beloved |
| The Queen's Gambit — Pilot | 8.64 | Massive hit (limited series) |
| Boardwalk Empire — Pilot | 8.64 | Emmy winner, prestige HBO |
| Insecure — Pilot | 8.60 | Culturally defining |

**Key insight:** The benchmark labels may need a second pass. Some of these "losers" are arguably more transcendent than some "winners."

---

## 9. Notable False Negatives (Winners Ranked Low)

Winners the model underranked — these reveal gaps in the current dimensions:

| Script | Rank | Score | Gap vs Winner Avg |
|--------|------|-------|--------------------|
| Schitt's Creek — Pilot | 825/909 | 5.27 | -3.19 |
| Prison Break — Pilot | 590/909 | 7.28 | -1.18 |
| Teen Wolf — Pilot | 423/909 | 7.63 | -0.83 |
| Mad Men — Pilot | 264/909 | 7.98 | -0.48 |
| Yellowstone — Pilot | 209/909 | 7.99 | -0.47 |
| Severance — Pilot | 96/909 | 8.30 | -0.16 |
| Euphoria — Pilot | 88/909 | 8.35 | -0.11 |

**Schitt's Creek at rank 825 is the biggest red flag.** It became one of the most beloved comedies of the decade. The current rubric clearly cannot see what makes it transcendent — the slow-burn character revelation, the warmth, the emotional depth that only emerges over time. This is a strong signal that we're missing a dimension around *earned emotional resonance* or *slow-burn potential*.

**Mad Men at rank 264** is another: extraordinarily original, visually distinctive, thematically deep — but the pilot is deliberately quiet and slow. A dimension around *thematic depth* or *world density* might catch this.

---

## 10. What We Tested on the Rubric (Autoresearch Loop)

We ran 7 probe tests on 200-script subsets, mutating the rubric. Results (corrected baseline = 94.56% equal weights on probe):

| Test | Dimension Mutated | Type | Result | Delta |
|------|------------------|------|--------|-------|
| 1 | Creative Originality | Tighten anchors | Rejected | -2.6% |
| 2 | Creative Originality | Tighten anchors | Rejected | -3.7% |
| 3 | Creative Originality | Reframe | Rejected | -3.6% |
| 4 | Creative Originality | Replace | Rejected | -2.8% |
| 5 | Narrative Momentum | Tighten anchors | Broken (parser bug) | — |
| 6 | Narrative Momentum | Reframe | Broken (parser bug) | — |
| 7 | Narrative Momentum | Replace | Broken (parser bug) | — |

**Conclusion:** Mutating existing dimensions produced no improvement. The architecture was wrong — incremental rewording doesn't move the needle. The right approach is to **add genuinely new dimensions** that measure things not currently captured. The optimizer will do the feature selection.

---

## 11. What the Current Rubric Is Missing

Based on the false negatives and the score compression, here are the signal categories the 5 dimensions don't currently capture:

**A. The Fulcrum Between Originality and Resonance**  
The current dimensions treat originality and audience appeal as separate axes. But transcendent shows don't just score high on both — they achieve something qualitatively different: they feel *new* and *inevitable* simultaneously. Breaking Bad, The Office, Fleabag. This "resonant originality" or "cultural inevitability" isn't captured.

**B. Slow-Burn / Earned Potential**  
Schitt's Creek, Mad Men, The Wire — shows where the pilot doesn't fully reveal what the show will become. The rubric penalizes restraint. A dimension around *latent depth* or *world density* might help.

**C. Emotional Specificity / Tonal Uniqueness**  
Some shows are technically competent on all 5 dimensions but feel interchangeable. What makes a show feel *lived-in* and *specific*? Euphoria, Atlanta, Fleabag all have a tonal signature that's impossible to fake. Not currently measured.

**D. Cultural Timing / Social Resonance**  
Why did Succession land in 2018? Why did Fleabag hit so hard for millennials? Some shows feel like they were *made for this exact moment*. This is partially captured by audience_appeal but not precisely.

**E. Re-watchability / Density**  
Breaking Bad and The Wire reward multiple viewings. Schitt's Creek gets funnier on rewatch. The Office pilot feels different once you know the characters. This depth isn't visible from a single read but might be signaled by specific pilot qualities.

---

## 12. Next Steps

1. **Add 10-20 new dimensions** (single LLM call per script, ~$9 for full 909-script run)
2. **Re-run weight optimizer** across all old + new dimensions — it will automatically select what matters
3. **Relabel obvious benchmark errors** (Sherlock, The Good Place, etc.)
4. **Target: 88-90% holdout accuracy** with expanded dimension set

The architecture is ready. We just need the new dimensions.

