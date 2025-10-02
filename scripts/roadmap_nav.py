"""Roadmap navigator utility for hierarchical phase structure."""

from __future__ import annotations

import sys
from pathlib import Path

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
        phases: dict[str, str] = {}
        if not ROADMAP_DIR.exists():
            return phases
        for phase_file in sorted(ROADMAP_DIR.glob("phase-*.md")):
            phase_num = phase_file.stem.replace("phase-", "").split("-")[0]
            phases[phase_num] = phase_file.read_text(encoding="utf-8")
        return phases

    def get_current_phase_number(self) -> str | None:
        """Extract current phase from index."""
        for line in self.index_content.splitlines():
            if line.startswith("**Current Phase:**"):
                # Example: "**Current Phase:** 13 — Advanced Strategy Toolkit 📋"
                parts = line.split(":", 1)[1].strip().split("—", 1)
                phase_num = parts[0].strip()
                # Remove any markdown formatting
                phase_num = phase_num.replace("**", "").strip()
                return phase_num
        return None

    def get_phase_content(self, phase_num: str) -> str | None:
        """Get full content of specific phase file."""
        phase_key = f"{int(phase_num):02d}"
        return self.phases.get(phase_key)

    def get_current_phase_content(self) -> str | None:
        """Get content of current phase."""
        current = self.get_current_phase_number()
        if current:
            return self.get_phase_content(current)
        return None

    def extract_sub_phases(self, phase_content: str) -> list[dict[str, str]]:
        """Extract sub-phase headings and status."""
        sub_phases = []
        for line in phase_content.splitlines():
            if line.startswith("### Phase "):
                parts = line.split("—", 1)
                number = parts[0].replace("### Phase", "").strip()
                title_status = parts[1].strip() if len(parts) > 1 else ""
                status = "📋"
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

    def extract_sub_phase_content(self, phase_content: str, sub_phase_number: str) -> str:
        """Extract content of specific sub-phase."""
        lines = phase_content.splitlines()
        start_idx = None
        for idx, line in enumerate(lines):
            if line.startswith(f"### Phase {sub_phase_number} "):
                start_idx = idx
                break
        if start_idx is None:
            return ""
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

        first_line = phase_content.splitlines()[0]
        print(f"📊 Current Phase Status: {first_line}")
        print(SEPARATOR)

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

        task_content = self.extract_sub_phase_content(phase_content, next_task["number"])
        lines = task_content.splitlines()

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


def main() -> None:
    """Main entry point."""
    try:
        mode = sys.argv[1] if len(sys.argv) > 1 else "status"
        nav = RoadmapNavigator()
        if mode == "status":
            nav.show_status()
        elif mode == "next":
            nav.show_next()
        else:
            print(f"Unknown mode: {mode}")
            print("Usage: python scripts/roadmap_nav.py [status|next]")
            sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
