#!/usr/bin/env bash
# test_pipeline.sh — GEM local smoke test
#
# Runs the full report pipeline on two already-scored corpus scripts
# (no API calls needed — uses --no-llm mode).
#
# Usage:
#   cd /path/to/autoresearch
#   chmod +x test_pipeline.sh
#   ./test_pipeline.sh
#
# When you're ready to test a FRESH unseen script with real scoring:
#   export OPENAI_API_KEY=your_key_here
#   python3 src/gem_eval.py path/to/your_pilot.pdf
#
# Or with a txt file:
#   python3 src/gem_eval.py path/to/your_pilot.txt --show-id "my-show-title-2026"

set -e

PASS=0
FAIL=0

run_test() {
    local label="$1"
    local cmd="$2"
    local expected_pattern="$3"

    printf "  %-50s" "$label"
    output=$(eval "$cmd" 2>&1)

    if echo "$output" | grep -q "$expected_pattern"; then
        echo "✓ PASS"
        PASS=$((PASS + 1))
    else
        echo "✗ FAIL"
        echo "    Expected pattern: $expected_pattern"
        echo "    Got: $(echo "$output" | head -5)"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "======================================================================"
echo "  GEM PIPELINE SMOKE TEST"
echo "======================================================================"
echo ""

# ── Test 1: Report for a strong corpus script ─────────────────────────────
python3 src/report_generator.py --show game-of-thrones-101-winter-is-coming-2011 --no-llm --json-only 2>/dev/null
run_test \
    "Strong script: Game of Thrones → STRONG SIGNAL or WORTH THE READ" \
    "python3 -c \"import json; r=json.load(open('data/reports/game-of-thrones-101-winter-is-coming-2011.json')); print(r['verdict']['label'])\"" \
    "STRONG SIGNAL\|WORTH THE READ"

# ── Test 2: Report for a weak corpus script ───────────────────────────────
python3 src/report_generator.py --show Street_Lawyer_1x01_-_Pilot --no-llm --json-only 2>/dev/null
run_test \
    "Weak script: Street Lawyer → PASS verdict" \
    "python3 -c \"import json; r=json.load(open('data/reports/Street_Lawyer_1x01_-_Pilot.json')); print(r['verdict']['label'])\"" \
    "PASS"

# ── Test 3: gem_eval.py with cached txt file ──────────────────────────────
# Copy a known script to simulate a fresh input
TMPID="smoke-test-$(date +%s)"
cp data/scoring/v3_expanded/per_script/breaking-bad-101-pilot-2008.json \
   data/scoring/v3_expanded/per_script/${TMPID}.json 2>/dev/null || true

run_test \
    "gem_eval.py: picks up cached score, generates report" \
    "python3 src/gem_eval.py data/extracted_text/breaking-bad-101-pilot-2008.txt --show-id ${TMPID} --no-llm --json-only 2>&1" \
    "Report"

# Cleanup temp files
rm -f data/scoring/v3_expanded/per_script/${TMPID}.json
rm -f data/reports/${TMPID}.json

# ── Test 4: JSON report file structure ────────────────────────────────────
run_test \
    "Report JSON has required keys (verdict, strengths, risks, dimensions)" \
    "python3 -c \"
import json
r = json.load(open('data/reports/breaking-bad-101-pilot-2008.json'))
keys = set(r.keys())
required = {'verdict','strengths','risks','dimensions','producer_takeaway'}
assert required.issubset(keys), f'Missing: {required - keys}'
print('OK')
\"" \
    "OK"

# ── Test 5: Percentile display sanity ─────────────────────────────────────
run_test \
    "Breaking Bad percentile ≥ 90th" \
    "python3 -c \"
import json
r = json.load(open('data/reports/breaking-bad-101-pilot-2008.json'))
pct = r['verdict']['percentile']
assert pct >= 90, f'Expected >=90, got {pct}'
print(f'percentile={pct} OK')
\"" \
    "percentile=.* OK"

# ── Test 6: Street Lawyer percentile ≤ 10th ───────────────────────────────
run_test \
    "Street Lawyer percentile ≤ 10th" \
    "python3 -c \"
import json
r = json.load(open('data/reports/Street_Lawyer_1x01_-_Pilot.json'))
pct = r['verdict']['percentile']
assert pct <= 10, f'Expected <=10, got {pct}'
print(f'percentile={pct} OK')
\"" \
    "percentile=.* OK"

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "======================================================================"
printf "  Results: %d passed, %d failed\n" $PASS $FAIL
echo "======================================================================"
echo ""

if [ $FAIL -gt 0 ]; then
    echo "  To test a real FRESH script (requires OPENAI_API_KEY):"
    echo "    export OPENAI_API_KEY=your_key"
    echo "    python3 src/gem_eval.py path/to/pilot.pdf"
    echo ""
    exit 1
else
    echo "  All tests passed."
    echo ""
    echo "  To evaluate a fresh script:"
    echo "    export OPENAI_API_KEY=your_key"
    echo "    python3 src/gem_eval.py path/to/pilot.pdf"
    echo ""
fi
