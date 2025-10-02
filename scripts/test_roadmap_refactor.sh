#!/usr/bin/env bash
set -euo pipefail

echo "🧪 Testing Roadmap Refactor Implementation"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass() {
  echo -e "${GREEN}✅ $1${NC}"
}

fail() {
  echo -e "${RED}❌ $1${NC}"
  exit 1
}

# Phase 1: Structure & Backup
echo "📁 Phase 1: Structure & Backup"
test -d roadmap/phases || fail "roadmap/phases directory missing"
test -d roadmap/templates || fail "roadmap/templates directory missing"
test -d roadmap/archive || fail "roadmap/archive directory missing"
test -f roadmap/archive/ROADMAP-monolith.md || fail "Backup missing"
pass "Structure and backup verified"
echo ""

# Phase 2: Phase Files
echo "📄 Phase 2: Phase File Extraction"
PHASE_COUNT=$(ls roadmap/phases/phase-*.md 2>/dev/null | wc -l)
[ "$PHASE_COUNT" -ge 13 ] || fail "Expected ≥13 phase files, got $PHASE_COUNT"
for f in roadmap/phases/phase-*.md; do
  basename "$f" | grep -qE '^phase-[0-9]{2}-.*\.md$' || fail "Invalid filename: $f"
done
test -f roadmap/phases/phase-13-strategies.md || fail "Phase 13 file missing"
PHASE13_LINES=$(wc -l < roadmap/phases/phase-13-strategies.md)
[ "$PHASE13_LINES" -ge 1000 ] || fail "Phase 13 too small ($PHASE13_LINES lines)"
pass "Phase files extracted and validated ($PHASE_COUNT files)"
echo ""

# Phase 3: ROADMAP.md Index
echo "📋 Phase 3: ROADMAP.md Index"
LINE_COUNT=$(wc -l < ROADMAP.md)
[ "$LINE_COUNT" -le 600 ] || fail "ROADMAP.md too large ($LINE_COUNT lines)"
grep -q "Current Phase.*13" ROADMAP.md || fail "Current phase not marked"
grep -q "## Phase Index" ROADMAP.md || fail "Phase index missing"
grep -q "roadmap/phases/phase-13-strategies.md" ROADMAP.md || fail "Phase 13 link missing"
pass "ROADMAP.md index verified ($LINE_COUNT lines)"
echo ""

# Phase 4: Navigator Utility
echo "🧭 Phase 4: Navigator Utility"
test -f scripts/roadmap_nav.py || fail "roadmap_nav.py missing"
./venv/bin/python -m py_compile scripts/roadmap_nav.py || fail "Syntax error in roadmap_nav.py"
./venv/bin/mypy scripts/roadmap_nav.py --strict 2>&1 | grep -q "Success" || fail "Type check failed"
./venv/bin/ruff check scripts/roadmap_nav.py || fail "Lint check failed"
CURRENT_PHASE=$(./venv/bin/python -c "import sys; sys.path.insert(0, 'scripts'); from roadmap_nav import RoadmapNavigator; nav = RoadmapNavigator(); print(nav.get_current_phase_number() or '')")
[ "$CURRENT_PHASE" = "13" ] || fail "Current phase detection failed (got: $CURRENT_PHASE)"
pass "Navigator utility verified"
echo ""

# Phase 5: Makefile Integration
echo "🔨 Phase 5: Makefile Integration"
set +o pipefail  # Disable pipefail for these tests
make status 2>&1 | grep -q "Phase 13" || fail "make status failed"
make next 2>&1 | grep -q "Planned Task" || fail "make next failed"
set -o pipefail  # Re-enable pipefail
make help >/dev/null 2>&1 || fail "make help broken"
pass "Makefile targets verified"
echo ""

# Phase 6: Documentation
echo "📚 Phase 6: Documentation Updates"
grep -q "roadmap/phases" AGENTS.md || fail "AGENTS.md not updated"
grep -q "roadmap/phases" CLAUDE.md || fail "CLAUDE.md not updated"
pass "Documentation updates verified"
echo ""

# Phase 7: Guardrails
echo "🛡️  Phase 7: Guardrails"
make fmt >/dev/null 2>&1 || fail "make fmt failed"
make lint >/dev/null 2>&1 || fail "make lint failed"
make type >/dev/null 2>&1 || fail "make type failed"
make test >/dev/null 2>&1 || fail "make test failed"
pass "All guardrails passed"
echo ""

# Phase 8: Rollback Readiness
echo "🔄 Phase 8: Rollback Readiness"
test -f roadmap/archive/ROADMAP-monolith.md || fail "Backup missing"
grep -q "## Phase 13" roadmap/archive/ROADMAP-monolith.md || fail "Backup corrupted"
pass "Rollback readiness verified"
echo ""

# Summary
echo "=========================================="
echo -e "${GREEN}🎉 ALL ACCEPTANCE TESTS PASSED${NC}"
echo ""
echo "Token Efficiency Metrics:"
echo "  - Original ROADMAP.md: $(wc -l < roadmap/archive/ROADMAP-monolith.md) lines"
echo "  - New index: $(wc -l < ROADMAP.md) lines"
echo "  - Phase 13: $(wc -l < roadmap/phases/phase-13-strategies.md) lines"
echo "  - Agent reads (index + phase): $(($(wc -l < ROADMAP.md) + $(wc -l < roadmap/phases/phase-13-strategies.md))) lines"
ORIGINAL_LINES=$(wc -l < roadmap/archive/ROADMAP-monolith.md)
NEW_LINES=$(($(wc -l < ROADMAP.md) + $(wc -l < roadmap/phases/phase-13-strategies.md)))
SAVINGS=$((100 - (NEW_LINES * 100 / ORIGINAL_LINES)))
echo "  - Token savings: ~${SAVINGS}%"
echo ""
echo "Next steps:"
echo "  1. Review changes: git status"
echo "  2. Test navigation: make status && make next"
echo "  3. Commit changes: git add . && git commit -m 'refactor(roadmap): split into hierarchical phase files'"
