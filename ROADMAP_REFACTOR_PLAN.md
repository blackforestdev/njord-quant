# Roadmap Refactor Plan — Hierarchical Phase Structure

**Goal:** Improve token efficiency and maintainability by splitting monolithic ROADMAP.md into phase-specific files.

**Current State:** ROADMAP.md (~9000 lines, ~35,000+ tokens)
**Target State:** ROADMAP.md index (~500 lines) + individual phase files (400-1500 lines each)
**Expected Token Savings:** 75-85% per agent interaction

---

## Directory Structure

```
njord_quant/
├── ROADMAP.md                          # Lightweight index (500 lines)
├── roadmap/
│   ├── README.md                       # Same as ROADMAP.md (symlink or copy)
│   ├── phases/
│   │   ├── phase-00-bootstrap.md       # ~400 lines
│   │   ├── phase-01-event-bus.md       # ~500 lines
│   │   ├── phase-02-risk-paper.md      # ~600 lines
│   │   ├── phase-04-market-data.md     # ~500 lines
│   │   ├── phase-05-backtester.md      # ~600 lines
│   │   ├── phase-06-portfolio.md       # ~500 lines
│   │   ├── phase-07-research-api.md    # ~800 lines
│   │   ├── phase-08-execution.md       # ~900 lines
│   │   ├── phase-09-telemetry.md       # ~800 lines
│   │   ├── phase-10-controller.md      # ~700 lines
│   │   ├── phase-11-monitoring.md      # ~800 lines
│   │   ├── phase-12-compliance.md      # ~850 lines
│   │   ├── phase-13-strategies.md      # ~1500 lines
│   │   ├── phase-14-simulation.md      # TBD
│   │   ├── phase-15-deployment.md      # TBD
│   │   └── phase-16-optimization.md    # TBD
│   ├── templates/
│   │   └── sub-phase-template.md       # Reusable template
│   └── archive/
│       └── ROADMAP-monolith.md         # Original 9000-line file (backup)
├── scripts/
│   ├── roadmap_nav.py                  # New: unified navigator utility
│   ├── show_status.py                  # Updated: use roadmap_nav
│   └── show_next.py                    # Updated: use roadmap_nav
└── Makefile                            # Updated: new targets
```

---

## New ROADMAP.md (Index File)

**Purpose:** Lightweight entry point for humans and agents

**Content:**
```markdown
# Njord Quant Development Roadmap

**Current Phase:** 13 — Advanced Strategy Toolkit 📋
**Last Updated:** 2025-10-02

## Quick Navigation

- [How to Use This Roadmap](#how-to-use-this-roadmap)
- [Phase Index](#phase-index)
- [Current Phase Details](roadmap/phases/phase-13-strategies.md)
- [Dependencies Graph](#dependencies-graph)
- [Task Template](roadmap/templates/sub-phase-template.md)

---

## How to Use This Roadmap

### For Humans
1. Check "Current Phase" above
2. Browse [Phase Index](#phase-index) below
3. Click phase link to view detailed specification
4. Use `make status` to see current task
5. Use `make next` to see next planned task

### For AI Agents
1. Read this index file (ROADMAP.md) to find current phase
2. Open corresponding phase file: `roadmap/phases/phase-XX-name.md`
3. Navigate to specific sub-phase
4. Execute per acceptance criteria
5. Update status emoji (📋 → 🚧 → ✅)

**Token Optimization:**
- Read ROADMAP.md (500 lines) → identify phase
- Read specific phase file (800-1500 lines) → find sub-phase
- **Total: ~2000 lines vs 9000 (78% reduction)**

---

## Phase Index

| Phase | Title | Status | Sub-Phases | Link |
|-------|-------|--------|------------|------|
| 0 | Bootstrap & Guardrails | ✅ | 4 | [phase-00-bootstrap.md](roadmap/phases/phase-00-bootstrap.md) |
| 1 | Event Bus & Market Data | ✅ | 5 | [phase-01-event-bus.md](roadmap/phases/phase-01-event-bus.md) |
| 2 | Risk Engine & Paper OMS | ✅ | 6 | [phase-02-risk-paper.md](roadmap/phases/phase-02-risk-paper.md) |
| 4 | Market Data Storage | ✅ | 4 | [phase-04-market-data.md](roadmap/phases/phase-04-market-data.md) |
| 5 | Backtester | ✅ | 5 | [phase-05-backtester.md](roadmap/phases/phase-05-backtester.md) |
| 6 | Portfolio Allocator | ✅ | 4 | [phase-06-portfolio.md](roadmap/phases/phase-06-portfolio.md) |
| 7 | Research API | ✅ | 9 | [phase-07-research-api.md](roadmap/phases/phase-07-research-api.md) |
| 8 | Execution Layer | 📋 | 9 | [phase-08-execution.md](roadmap/phases/phase-08-execution.md) |
| 9 | Metrics & Telemetry | 📋 | 10 | [phase-09-telemetry.md](roadmap/phases/phase-09-telemetry.md) |
| 10 | Live Trade Controller | 📋 | 8 | [phase-10-controller.md](roadmap/phases/phase-10-controller.md) |
| 11 | Monitoring & Alerts | 📋 | 10 | [phase-11-monitoring.md](roadmap/phases/phase-11-monitoring.md) |
| 12 | Compliance & Audit | 📋 | 9 | [phase-12-compliance.md](roadmap/phases/phase-12-compliance.md) |
| 13 | Advanced Strategy Toolkit | 📋 | 10 | [phase-13-strategies.md](roadmap/phases/phase-13-strategies.md) |
| 14 | Simulation Harness | 📋 | TBD | [phase-14-simulation.md](roadmap/phases/phase-14-simulation.md) |
| 15 | Deployment Framework | 📋 | TBD | [phase-15-deployment.md](roadmap/phases/phase-15-deployment.md) |
| 16 | Optimization Pass | 📋 | TBD | [phase-16-optimization.md](roadmap/phases/phase-16-optimization.md) |

---

## Dependencies Graph

```
Phase 0 (Bootstrap) ✅
    └─> Phase 1 (Event Bus) ✅
            └─> Phase 2 (Risk & Paper) ✅
                    └─> Phase 4 (Market Data) ✅
                            └─> Phase 5 (Backtester) ✅
                                    └─> Phase 6 (Portfolio) ✅
                                            └─> Phase 7 (Research) ✅
                                                    └─> Phase 8 (Execution) 📋
                                                            └─> Phase 9 (Telemetry) 📋
                                                                    └─> Phase 10 (Controller) 📋
                                                                            └─> Phase 11 (Monitoring) 📋
                                                                                    └─> Phase 12 (Compliance) 📋
                                                                                            └─> Phase 13 (Strategies) 📋
                                                                                                    └─> Phase 14 (Simulation) 📋
                                                                                                            └─> Phase 15 (Deployment) 📋
                                                                                                                    └─> Phase 16 (Optimization) 📋
```

---

## Current Phase Summary

**Phase 13 — Advanced Strategy Toolkit** 📋

Advanced quantitative strategies with factor models, ML feature engineering, and ensemble meta-strategies.

**Sub-Phases:**
- 13.0: Factor Model Contracts
- 13.1: Momentum Factor Calculator
- 13.2: Mean Reversion Factor Calculator
- 13.3: Carry & Volatility Factors
- 13.4: Volume & Microstructure Factors
- 13.5: ML Feature Engineering Pipeline (offline only)
- 13.6: Factor Scoring Strategy
- 13.7: Statistical Arbitrage Strategy
- 13.8: Ensemble Meta-Strategy
- 13.9: Regime-Adaptive Strategy
- 13.10: Advanced Strategy Documentation

**Full Details:** [roadmap/phases/phase-13-strategies.md](roadmap/phases/phase-13-strategies.md)

---

## Status Legend

| Emoji | Meaning |
|-------|---------|
| ✅ | Complete (all tests passing) |
| 🚧 | In Progress (partial implementation) |
| 📋 | Planned (not started) |
| ⚠️ | Blocked (dependency issue) |
| 🔄 | Rework Needed (failing tests/review) |

---

## Make Targets

```bash
# View this index
make roadmap

# Show current phase status
make status

# Show next planned task
make next

# Open current phase file directly
make phase-current
```

---

**Last Updated:** 2025-10-02
**Maintained By:** Njord Trust
**License:** Proprietary
```

**Estimated Lines:** ~500 lines

---

## scripts/roadmap_nav.py (New Utility)

**Purpose:** Unified navigator for hierarchical roadmap structure

```python
"""Roadmap navigator utility for hierarchical phase structure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

ROADMAP_INDEX = Path("ROADMAP.md")
ROADMAP_DIR = Path("roadmap/phases")
SEPARATOR = "━" * 80


class RoadmapNavigator:
    """Navigate hierarchical roadmap structure."""

    def __init__(self) -> None:
        if not ROADMAP_INDEX.exists():
            raise FileNotFoundError(f"{ROADMAP_INDEX} not found")
        self.index_content = ROADMAP_INDEX.read_text(encoding="utf-8")
        self.phases = self._load_all_phases()

    def _load_all_phases(self) -> dict[str, str]:
        """Load all phase files into memory."""
        phases = {}
        if not ROADMAP_DIR.exists():
            return phases
        for phase_file in sorted(ROADMAP_DIR.glob("phase-*.md")):
            phase_num = phase_file.stem.replace("phase-", "")
            phases[phase_num] = phase_file.read_text(encoding="utf-8")
        return phases

    def get_current_phase_number(self) -> str | None:
        """Extract current phase from index."""
        for line in self.index_content.splitlines():
            if line.startswith("**Current Phase:**"):
                # Example: "**Current Phase:** 13 — Advanced Strategy Toolkit 📋"
                parts = line.split(":", 1)[1].strip().split("—", 1)
                return parts[0].strip()
        return None

    def get_phase_status(self, phase_num: str) -> str:
        """Get phase status emoji (✅/🚧/📋)."""
        for line in self.index_content.splitlines():
            if f"| {phase_num} |" in line or f"| 0{phase_num} |" in line:
                if "✅" in line:
                    return "✅"
                elif "🚧" in line:
                    return "🚧"
                elif "📋" in line:
                    return "📋"
                elif "⚠️" in line:
                    return "⚠️"
                elif "🔄" in line:
                    return "🔄"
        return "❓"

    def get_phase_content(self, phase_num: str) -> str | None:
        """Get full content of specific phase file."""
        # Normalize to 2-digit format
        phase_key = f"{int(phase_num):02d}"
        return self.phases.get(phase_key)

    def get_current_phase_content(self) -> str | None:
        """Get content of current phase."""
        current = self.get_current_phase_number()
        if current:
            return self.get_phase_content(current)
        return None

    def find_next_planned_phase(self) -> str | None:
        """Find next phase with 📋 status."""
        for line in self.index_content.splitlines():
            if line.startswith("| ") and "📋" in line:
                parts = line.split("|")
                if len(parts) > 1:
                    return parts[1].strip()
        return None

    def extract_sub_phases(self, phase_content: str) -> list[dict[str, str]]:
        """Extract sub-phase headings and status."""
        sub_phases = []
        for line in phase_content.splitlines():
            if line.startswith("### Phase "):
                # Example: "### Phase 13.5 — ML Feature Engineering Pipeline 📋"
                parts = line.split("—", 1)
                number = parts[0].replace("### Phase", "").strip()
                title_status = parts[1].strip() if len(parts) > 1 else ""
                status = "📋"  # Default
                for emoji in ["✅", "🚧", "📋", "⚠️", "🔄"]:
                    if emoji in title_status:
                        status = emoji
                        break
                title = title_status.replace(status, "").strip()
                sub_phases.append({"number": number, "title": title, "status": status})
        return sub_phases

    def find_first_incomplete_sub_phase(
        self, sub_phases: list[dict[str, str]]
    ) -> dict[str, str] | None:
        """Find first sub-phase not marked ✅."""
        for sub_phase in sub_phases:
            if sub_phase["status"] != "✅":
                return sub_phase
        return None

    def extract_sub_phase_content(
        self, phase_content: str, sub_phase_number: str
    ) -> str:
        """Extract content of specific sub-phase."""
        lines = phase_content.splitlines()
        start_idx = None
        for idx, line in enumerate(lines):
            if line.startswith(f"### Phase {sub_phase_number} "):
                start_idx = idx
                break
        if start_idx is None:
            return ""
        # Find next sub-phase or end of file
        end_idx = len(lines)
        for idx in range(start_idx + 1, len(lines)):
            if lines[idx].startswith("### Phase ") or lines[idx].startswith("## "):
                end_idx = idx
                break
        return "\n".join(lines[start_idx:end_idx])

    def show_status(self) -> None:
        """Show current phase status (for make status)."""
        current = self.get_current_phase_number()
        if not current:
            print("📊 Current Phase Status: Unknown")
            return

        phase_content = self.get_phase_content(current)
        if not phase_content:
            print(f"📊 Current Phase {current}: File not found")
            return

        # Extract phase title
        first_line = phase_content.splitlines()[0]
        print(f"📊 Current Phase Status: {first_line}")
        print(SEPARATOR)

        # Show sub-phases
        sub_phases = self.extract_sub_phases(phase_content)
        if not sub_phases:
            print("No sub-phases found")
        else:
            for sp in sub_phases:
                print(f"  {sp['status']} Phase {sp['number']} — {sp['title']}")

        print(SEPARATOR)
        print()
        print("Legend: ✅ Complete | 🚧 In Progress | 📋 Planned | ⚠️ Blocked | 🔄 Rework")
        print()
        print(f"For full details: cat roadmap/phases/phase-{int(current):02d}-*.md")

    def show_next(self) -> None:
        """Show next planned task (for make next)."""
        print("📈 Phase Progress:")
        # Show all phases with status
        for line in self.index_content.splitlines():
            if line.startswith("| ") and "|" in line[2:]:
                parts = line.split("|")
                if len(parts) > 3 and parts[1].strip().isdigit():
                    phase_num = parts[1].strip()
                    title = parts[2].strip()
                    status = "📋"
                    for emoji in ["✅", "🚧", "📋", "⚠️", "🔄"]:
                        if emoji in parts[3]:
                            status = emoji
                            break
                    print(f"  Phase {phase_num:>2}: {title:<40} {status}")

        print()
        print("🎯 Next Planned Task:")
        print(SEPARATOR)

        current = self.get_current_phase_number()
        if not current:
            print("No current phase identified")
            print(SEPARATOR)
            return

        phase_content = self.get_phase_content(current)
        if not phase_content:
            print(f"Phase {current} file not found")
            print(SEPARATOR)
            return

        sub_phases = self.extract_sub_phases(phase_content)
        next_task = self.find_first_incomplete_sub_phase(sub_phases)

        if not next_task:
            print("All tasks in current phase are complete!")
            print(SEPARATOR)
            return

        # Extract and display next task details
        task_content = self.extract_sub_phase_content(
            phase_content, next_task["number"]
        )
        lines = task_content.splitlines()

        # Show up to 40 lines or until "**Acceptance:**"
        max_lines = 40
        output_lines = []
        for line in lines[:max_lines]:
            output_lines.append(line)
            if line.startswith("**Acceptance:**"):
                break

        print("\n".join(output_lines))
        if len(lines) > len(output_lines):
            print("... (see phase file for full details)")
        print(SEPARATOR)
        print()
        print(f"Full spec: roadmap/phases/phase-{int(current):02d}-*.md")


def main(mode: Literal["status", "next"] = "status") -> None:
    """Main entry point."""
    try:
        nav = RoadmapNavigator()
        if mode == "status":
            nav.show_status()
        elif mode == "next":
            nav.show_next()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    import sys

    mode_arg = sys.argv[1] if len(sys.argv) > 1 else "status"
    main(mode_arg)  # type: ignore
```

**Estimated Lines:** ~250 lines

---

## Updated Makefile Targets

```makefile
# Roadmap navigation targets
roadmap:
	@if [ ! -f ROADMAP.md ]; then \
		echo "Error: ROADMAP.md not found"; \
		exit 1; \
	fi
	@echo "📋 Opening ROADMAP.md (index)..."
	@less ROADMAP.md

status:
	@PY_CMD=$$( [ -x "$(PY)" ] && echo "$(PY)" || command -v python3 || command -v python ); \
	if [ -z "$$PY_CMD" ]; then \
		echo "Error: Python interpreter not found"; \
		exit 1; \
	fi; \
	$$PY_CMD scripts/roadmap_nav.py status

next:
	@PY_CMD=$$( [ -x "$(PY)" ] && echo "$(PY)" || command -v python3 || command -v python ); \
	if [ -z "$$PY_CMD" ]; then \
		echo "Error: Python interpreter not found"; \
		exit 1; \
	fi; \
	$$PY_CMD scripts/roadmap_nav.py next
	@echo ""
	@echo "To implement: Review task in phase file, then run:"
	@echo "  make fmt && make lint && make type && make test"

phase-current:
	@PY_CMD=$$( [ -x "$(PY)" ] && echo "$(PY)" || command -v python3 || command -v python ); \
	if [ -z "$$PY_CMD" ]; then \
		echo "Error: Python interpreter not found"; \
		exit 1; \
	fi; \
	PHASE_NUM=$$($$PY_CMD -c "from scripts.roadmap_nav import RoadmapNavigator; nav = RoadmapNavigator(); print(nav.get_current_phase_number() or '')"); \
	if [ -z "$$PHASE_NUM" ]; then \
		echo "Error: Could not determine current phase"; \
		exit 1; \
	fi; \
	PHASE_FILE=$$(printf "roadmap/phases/phase-%02d-*.md" $$PHASE_NUM); \
	ls $$PHASE_FILE 2>/dev/null | head -1 | xargs less

phase:
	@if [ -z "$(NUM)" ]; then \
		echo "Usage: make phase NUM=13"; \
		exit 1; \
	fi; \
	PHASE_FILE=$$(printf "roadmap/phases/phase-%02d-*.md" $(NUM)); \
	ls $$PHASE_FILE 2>/dev/null | head -1 | xargs less || echo "Phase $(NUM) not found"
```

---

## Migration Steps

### Step 1: Create Directory Structure
```bash
mkdir -p roadmap/phases roadmap/templates roadmap/archive
```

### Step 2: Extract Phase Files
Create `scripts/split_roadmap.py`:
```python
"""Split monolithic ROADMAP.md into phase files."""

from pathlib import Path


def split_roadmap() -> None:
    roadmap = Path("ROADMAP.md").read_text(encoding="utf-8")
    lines = roadmap.splitlines()

    # Find all phase headers
    phase_indices = [idx for idx, line in enumerate(lines) if line.startswith("## Phase ")]

    output_dir = Path("roadmap/phases")
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, start_idx in enumerate(phase_indices):
        # Determine phase number and title
        phase_line = lines[start_idx]
        # Example: "## Phase 13 — Advanced Strategy Toolkit 📋"
        phase_num_str = phase_line.split("—")[0].replace("## Phase", "").strip()
        try:
            phase_num = int(phase_num_str.split(".")[0])
        except ValueError:
            continue

        # Find title for filename
        title_part = phase_line.split("—", 1)[1] if "—" in phase_line else f"phase-{phase_num}"
        title_slug = title_part.split()[0].lower().replace(" ", "-") if title_part else f"phase{phase_num}"

        # Find end of this phase (next phase header or end of file)
        end_idx = phase_indices[i + 1] if i + 1 < len(phase_indices) else len(lines)

        # Extract content
        phase_content = "\n".join(lines[start_idx:end_idx])

        # Write to file
        output_file = output_dir / f"phase-{phase_num:02d}-{title_slug}.md"
        output_file.write_text(phase_content, encoding="utf-8")
        print(f"Created: {output_file}")


if __name__ == "__main__":
    split_roadmap()
```

### Step 3: Backup Original
```bash
cp ROADMAP.md roadmap/archive/ROADMAP-monolith.md
git add roadmap/archive/ROADMAP-monolith.md
git commit -m "backup: archive monolithic ROADMAP.md before split"
```

### Step 4: Run Split Script
```bash
python scripts/split_roadmap.py
```

### Step 5: Create New ROADMAP.md Index
```bash
# Use content from "New ROADMAP.md (Index File)" section above
```

### Step 6: Create Navigator Utility
```bash
# Use content from "scripts/roadmap_nav.py" section above
```

### Step 7: Update Makefile
```bash
# Apply changes from "Updated Makefile Targets" section above
```

### Step 8: Update Documentation References
- Update AGENTS.md: Reference new structure
- Update CLAUDE.md: Reference new structure
- Add note about hierarchical navigation

### Step 9: Test
```bash
make status
make next
make phase-current
make phase NUM=13
```

### Step 10: Commit
```bash
git add roadmap/ scripts/roadmap_nav.py ROADMAP.md Makefile AGENTS.md CLAUDE.md
git commit -m "refactor(roadmap): split into hierarchical phase files for token efficiency"
```

---

## Expected Benefits

### Token Efficiency
| Operation | Before | After | Savings |
|-----------|--------|-------|---------|
| Find current task | 9000 lines | 500 + 1500 = 2000 | **78%** |
| Check dependencies | 9000 lines | 500 + 200 = 700 | **92%** |
| Review sub-phase | 9000 lines | 1500 (phase file) | **83%** |
| Update status | 9000 lines | 1500 (phase file) | **83%** |

### Maintainability
- ✅ Parallel development (no merge conflicts)
- ✅ Granular version control (phase-level commits)
- ✅ Easy rollback (revert single file)
- ✅ Archive completed phases (reduce scope)
- ✅ Faster git operations (smaller diffs)

### Developer Experience
- ✅ Faster `make status` / `make next` (less parsing)
- ✅ Direct phase file access (`make phase NUM=13`)
- ✅ Cleaner navigation (table of contents in index)
- ✅ Better IDE integration (smaller files)

---

## Rollback Plan

If issues arise:
```bash
# Restore original
git checkout HEAD~1 ROADMAP.md
git rm -rf roadmap/
git checkout HEAD~1 Makefile scripts/show_status.py scripts/show_next.py

# Or use backup
cp roadmap/archive/ROADMAP-monolith.md ROADMAP.md
```

---

## Acceptance Criteria

### **Phase 1: Structure & Backup**
- ✅ Directory structure created: `roadmap/{phases,templates,archive}`
- ✅ Original ROADMAP.md backed up to `roadmap/archive/ROADMAP-monolith.md`
- ✅ Git status clean before starting split
- ✅ Backup committed to git

**Test:**
```bash
test -d roadmap/phases || exit 1
test -d roadmap/templates || exit 1
test -d roadmap/archive || exit 1
test -f roadmap/archive/ROADMAP-monolith.md || exit 1
diff ROADMAP.md roadmap/archive/ROADMAP-monolith.md || exit 1  # Should be identical
```

---

### **Phase 2: Phase File Extraction**
- ✅ All 13 active phases split into individual files
- ✅ File naming convention: `phase-XX-<slug>.md` (XX = 2-digit phase number)
- ✅ Each phase file contains complete section from original
- ✅ No content loss (total lines match original ±10 lines for formatting)
- ✅ All sub-phases preserved with correct headings
- ✅ Status emojis preserved (✅/🚧/📋)

**Test:**
```bash
# Count phase files (should be 13+)
PHASE_COUNT=$(ls roadmap/phases/phase-*.md 2>/dev/null | wc -l)
[ "$PHASE_COUNT" -ge 13 ] || { echo "Error: Expected ≥13 phase files, got $PHASE_COUNT"; exit 1; }

# Verify file naming convention
for f in roadmap/phases/phase-*.md; do
  basename "$f" | grep -qE '^phase-[0-9]{2}-[a-z-]+\.md$' || { echo "Error: Invalid filename $f"; exit 1; }
done

# Verify Phase 13 (strategies) exists and has content
test -f roadmap/phases/phase-13-strategies.md || exit 1
wc -l roadmap/phases/phase-13-strategies.md | awk '{if ($1 < 1000) exit 1}'  # Should be ~1500 lines

echo "✅ Phase files extraction verified"
```

---

### **Phase 3: New ROADMAP.md Index**
- ✅ New ROADMAP.md created (≤600 lines)
- ✅ Contains phase index table with all phases
- ✅ Current phase marked correctly (Phase 13)
- ✅ All phase links valid (point to existing files)
- ✅ Dependencies graph present
- ✅ Status legend present
- ✅ Agent instructions clear

**Test:**
```bash
# Size check
LINE_COUNT=$(wc -l < ROADMAP.md)
[ "$LINE_COUNT" -le 600 ] || { echo "Error: ROADMAP.md too large ($LINE_COUNT lines)"; exit 1; }

# Content checks
grep -q "**Current Phase:** 13" ROADMAP.md || exit 1
grep -q "## Phase Index" ROADMAP.md || exit 1
grep -q "## Dependencies Graph" ROADMAP.md || exit 1
grep -q "## Status Legend" ROADMAP.md || exit 1

# Link validation (check Phase 13 link exists)
grep -q "roadmap/phases/phase-13-strategies.md" ROADMAP.md || exit 1

echo "✅ ROADMAP.md index verified"
```

---

### **Phase 4: Navigator Utility**
- ✅ `scripts/roadmap_nav.py` created
- ✅ RoadmapNavigator class implemented
- ✅ Methods: `get_current_phase_number()`, `get_phase_content()`, `show_status()`, `show_next()`
- ✅ Handles missing files gracefully (no crashes)
- ✅ Type hints present (mypy strict compliance)
- ✅ Passes linting (ruff)

**Test:**
```bash
# File exists and is executable
test -f scripts/roadmap_nav.py || exit 1

# Python syntax check
./venv/bin/python -m py_compile scripts/roadmap_nav.py || exit 1

# Type check
./venv/bin/mypy scripts/roadmap_nav.py --strict || exit 1

# Lint check
./venv/bin/ruff check scripts/roadmap_nav.py || exit 1

# Functional test: get current phase
CURRENT_PHASE=$(./venv/bin/python scripts/roadmap_nav.py status 2>&1 | grep -oP 'Phase \K[0-9]+' | head -1)
[ "$CURRENT_PHASE" = "13" ] || { echo "Error: Current phase should be 13, got $CURRENT_PHASE"; exit 1; }

echo "✅ Navigator utility verified"
```

---

### **Phase 5: Makefile Integration**
- ✅ `make status` uses `scripts/roadmap_nav.py status`
- ✅ `make next` uses `scripts/roadmap_nav.py next`
- ✅ `make roadmap` opens new ROADMAP.md index
- ✅ New target: `make phase-current` opens current phase file
- ✅ New target: `make phase NUM=X` opens specific phase file
- ✅ All targets work without errors
- ✅ Backwards compatible (no breaking changes to existing targets)

**Test:**
```bash
# Test make status
make status 2>&1 | grep -q "Phase 13" || { echo "Error: make status failed"; exit 1; }

# Test make next
make next 2>&1 | grep -q "Next Planned Task" || { echo "Error: make next failed"; exit 1; }

# Test make phase NUM=13
make phase NUM=13 2>&1 | head -5 | grep -q "Phase 13" || { echo "Error: make phase failed"; exit 1; }

# Verify no breakage of other targets
make help >/dev/null 2>&1 || { echo "Error: make help broken"; exit 1; }

echo "✅ Makefile integration verified"
```

---

### **Phase 6: Documentation Updates**
- ✅ AGENTS.md updated with hierarchical roadmap instructions
- ✅ CLAUDE.md updated with new navigation workflow
- ✅ References to "ROADMAP.md" clarified (index vs phase files)
- ✅ Agent workflow examples provided

**Test:**
```bash
# Check AGENTS.md mentions new structure
grep -q "roadmap/phases" AGENTS.md || exit 1
grep -q "phase-specific files" AGENTS.md || exit 1

# Check CLAUDE.md mentions new structure
grep -q "roadmap/phases" CLAUDE.md || exit 1

echo "✅ Documentation updates verified"
```

---

### **Phase 7: End-to-End Validation**
- ✅ All guardrails pass: `make fmt && make lint && make type && make test`
- ✅ No regressions (all existing tests pass)
- ✅ Git status clean (no untracked files except intended additions)
- ✅ Total line count reduced: original ~9000 → index ~500 + largest phase ~1500 = ~2000
- ✅ Token efficiency demonstrated (agent reads <2500 lines vs 9000)

**Test:**
```bash
# Guardrails
make fmt || exit 1
make lint || exit 1
make type || exit 1
make test || exit 1

# Line count validation
ROADMAP_LINES=$(wc -l < ROADMAP.md)
[ "$ROADMAP_LINES" -le 600 ] || { echo "Error: Index too large"; exit 1; }

PHASE13_LINES=$(wc -l < roadmap/phases/phase-13-strategies.md)
[ "$PHASE13_LINES" -ge 1000 ] && [ "$PHASE13_LINES" -le 2000 ] || { echo "Error: Phase 13 size unexpected"; exit 1; }

# Git status (should only see intended changes)
git status --porcelain | grep -qE '^(A|M)' || exit 1  # Should have additions/modifications

echo "✅ End-to-end validation passed"
```

---

### **Phase 8: Rollback Readiness**
- ✅ Original ROADMAP.md preserved in `roadmap/archive/ROADMAP-monolith.md`
- ✅ Rollback procedure documented
- ✅ Git tags created for pre/post refactor states

**Test:**
```bash
# Verify backup exists and is valid markdown
test -f roadmap/archive/ROADMAP-monolith.md || exit 1
grep -q "## Phase 13" roadmap/archive/ROADMAP-monolith.md || exit 1

# Verify can restore (dry-run)
cp roadmap/archive/ROADMAP-monolith.md /tmp/test-restore.md
diff /tmp/test-restore.md roadmap/archive/ROADMAP-monolith.md || exit 1

echo "✅ Rollback readiness verified"
```

---

## Master Acceptance Test Script

**File:** `scripts/test_roadmap_refactor.sh`

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "🧪 Testing Roadmap Refactor Implementation"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

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
grep -q "**Current Phase:** 13" ROADMAP.md || fail "Current phase not marked"
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
CURRENT_PHASE=$(./venv/bin/python -c "from scripts.roadmap_nav import RoadmapNavigator; nav = RoadmapNavigator(); print(nav.get_current_phase_number() or '')")
[ "$CURRENT_PHASE" = "13" ] || fail "Current phase detection failed (got: $CURRENT_PHASE)"
pass "Navigator utility verified"
echo ""

# Phase 5: Makefile Integration
echo "🔨 Phase 5: Makefile Integration"
make status 2>&1 | grep -q "Phase 13" || fail "make status failed"
make next 2>&1 | grep -q "Next Planned Task" || fail "make next failed"
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
```

---

## Definition of Done

**All acceptance criteria must pass:**
- ✅ All 8 phases pass validation tests
- ✅ Master test script exits with code 0
- ✅ `make fmt && make lint && make type && make test` all green
- ✅ `make status` and `make next` function correctly
- ✅ Token savings ≥75% demonstrated
- ✅ No content loss (all sub-phases preserved)
- ✅ Rollback procedure validated
- ✅ Git history clean with atomic commits

**Audit Requirements:**
1. **Correctness:** All phase content preserved from original
2. **Completeness:** All 13 phases split with no orphaned content
3. **Consistency:** File naming, status emojis, formatting uniform
4. **Compatibility:** Existing make targets continue to work
5. **Safety:** Backup exists, rollback procedure tested
6. **Performance:** Token usage reduced by ≥75%

---

### Polish Backlog (Phase 16 Sweep Targets)

- Revalidate external consumers of the new `(allowed, reason)` return signature in `RiskEngine.handle_intent`
- Consider increasing iterations in the instrumentation performance benchmark to reduce flakiness risk
- Add docstrings indicating metrics emission on instrumented service methods
- Reconfirm `StrategyManager` metrics once dependent services are fully instrumented

---

**Status:** Ready for implementation with acceptance criteria
**Estimated Effort:** 2-3 hours
**Risk:** Low (backup created, rollback plan in place, comprehensive tests)
