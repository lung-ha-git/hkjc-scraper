#!/bin/bash
# HKJC Pipeline Pre-Commit Hook
# Runs BEFORE every git commit:
#   1. Field consistency tests (pipeline field name checks)
#   2. Webapp API tests (Express.js endpoint checks)
#
# Installation:
#   cp pre-commit-hook.sh .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
#
# Manual run:
#   bash pre-commit-hook.sh

set -e

PROJECT_ROOT="/Users/fatlung/ClawObsidian/Claw/The_Brain/Projects/HKJC"
REPORT_FILE="$PROJECT_ROOT/reports/pre_commit_test_$(date +%Y%m%d_%H%M%S).txt"
mkdir -p "$PROJECT_ROOT/reports"

echo ""
echo "============================================================"
echo "  🧪 HKJC Pre-Commit Tests"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo ""

FAILED=0

# ─── Test 1: Field Consistency ────────────────────────────────────────

echo "━━━ [1/2] Field Consistency Tests ━━━"
echo "   FixtureScraper → sync_fixtures → racecards → odds"
echo ""

if python3 "$PROJECT_ROOT/src/tests/test_field_consistency.py" 2>&1 | tee -a "$REPORT_FILE"; then
    echo "   ✅ Field consistency tests PASSED"
else
    echo "   ❌ Field consistency tests FAILED"
    FAILED=1
fi

echo ""

# ─── Test 2: Webapp API Tests ─────────────────────────────────────────

echo "━━━ [2/2] Webapp API Tests ━━━"
echo "   /api/health, /api/fixtures, /api/racecards, /api/races"
echo ""

if python3 "$PROJECT_ROOT/src/tests/test_webapp_api.py" 2>&1 | tee -a "$REPORT_FILE"; then
    echo "   ✅ Webapp API tests PASSED"
else
    echo "   ❌ Webapp API tests FAILED"
    FAILED=1
fi

echo ""
echo "============================================================"
if [ $FAILED -eq 0 ]; then
    echo "  ✅ ALL TESTS PASSED — Commit safe to proceed"
    echo ""
    echo "  Report: $REPORT_FILE"
else
    echo "  ❌ TESTS FAILED — Fix issues before committing"
    echo ""
    echo "  Full report: $REPORT_FILE"
fi
echo "============================================================"
echo ""

exit $FAILED
