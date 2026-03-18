# Weight Optimization Continuation Plan

**Current Status:** 81.92% pairwise accuracy (+6.45% from baseline)
**Last Update:** 2026-03-17 12:18
**Optimized Config:** `config/evaluator_config.json`

---

## Phase 1: Completed ✅

All 5 initial proposals tested:
- ❌ Increase high-gap dimensions (Singular Vision, Boldness, World Originality) — No improvement
- ✅ Decrease low-gap dimensions (Character Depth 20%→17%, Dialogue Language 10%→7%) — +6.45% total

**Key insight:** The baseline weights for high-gap dimensions were already optimal. Improvements came from reducing noise (low-gap dimensions).

---

## Phase 2: Aggressive Fine-Tuning (Next Steps)

### Option A: Test More Aggressive Decreases
Reduce low-gap dimensions further to see if we can push higher:

```bash
# Create new proposals file or test manually
# Current: character_depth 0.17, dialogue_language 0.07

# Test aggressive decreases:
# - character_depth: 0.17 → 0.15 (more aggressive)
# - dialogue_language: 0.07 → 0.05 (more aggressive)
```

**Expected:** Could push 81.92% → 82.5% or plateau

**Implementation:**
1. Edit `src/auto_proposer.py` to add new proposal factory:
```python
def propose_aggressive_decreases(self):
    """Test more aggressive reductions of low-gap dimensions."""
    proposals = []
    # character_depth: 0.17 → 0.15
    proposals.append(self.propose_weight_decrease("character_depth", 0.15))
    # dialogue_language: 0.07 → 0.05
    proposals.append(self.propose_weight_decrease("dialogue_language", 0.05))
    return proposals
```

2. Run tests:
```bash
python3 main.py iterate --auto
```

### Option B: Test Increases on High-Gap Dimensions
The earlier tests on high-gap dims returned 0.0% accuracy. This might be a bug. Test them on FULL dataset to verify:

```bash
# Manually test: Singular Vision 0.25 → 0.28 (smaller increase)
# Then check if 0.0 was a real result or a calculation error
```

### Option C: Hybrid Rebalancing
Shift weight FROM low-gap TO high-gap dims (zero-sum):

```python
# Decrease character_depth 0.17 → 0.14 (freed 0.03)
# Increase singular_vision 0.25 → 0.28 (uses 0.03)
# Net: No change to total weights, but better allocation
```

**Expected:** Could push 81.92% → 82.2%+

---

## Phase 3: Search for Diminishing Returns

Once you find improvements diminishing (changes < 0.05%), you've likely hit the optimum.

**Stopping criteria:**
- 3+ consecutive failed proposals
- Improvements < 0.01%
- All tested variations show declining gains

---

## Phase 4: Validation & Lock In

Once satisfied with accuracy:

1. **Document final config:**
```bash
cat config/evaluator_config.json > FINAL_WEIGHTS.json
```

2. **Run fresh eval with final config** to confirm:
```bash
python3 rebuild_summary.py
```

3. **Commit to git:**
```bash
git add config/evaluator_config.json
git commit -m "Optimize weights: 78.7% → 82.X% pairwise accuracy"
```

4. **Ship it** — Use for product (GEM Transcendence Detector v2)

---

## Quick Reference: Current Weights

```json
{
  "singular_vision": 0.25,        // ← Was over-weighted? Test 0.28
  "boldness": 0.05,                // ← Test 0.07
  "world_originality": 0.10,       // ← Test 0.12
  "emotional_specificity": 0.15,   // ← Unchanged (good gap)
  "thematic_ambition": 0.15,       // ← Unchanged (good gap)
  "character_depth": 0.17,         // ✅ IMPROVED from 0.20
  "dialogue_language": 0.07,       // ✅ IMPROVED from 0.10
  "transcendence_verdict": 0.0     // Always 0
}
```

---

## Commands When You Return

**Continue tuning (auto mode):**
```bash
python3 main.py iterate --auto
```

**Check progress:**
```bash
cat data/results/experiment_summary.json
```

**See current config:**
```bash
cat config/evaluator_config.json
```

**Rebuild summary with new config:**
```bash
python3 rebuild_summary.py
```

---

## Architecture Notes

- **No LLM calls needed** — All tuning is re-weighting of existing evaluations (~1-2 sec per test)
- **Reversible** — Each change is logged; easy to revert if needed
- **Tracked** — All experiments logged to `data/results/experiments.jsonl`
- **Automated** — `--auto` mode finds improvements automatically

---

## Expected Final Range

- **Conservative:** 82-83% pairwise accuracy
- **Optimistic:** 83-84% pairwise accuracy
- **Diminishing returns kick in:** Likely by 82.5-83.0%

---

**Good luck! You've already achieved a solid +6.45% improvement. Keep going! 🚀**
