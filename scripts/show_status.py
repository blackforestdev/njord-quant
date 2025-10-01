"""Utility to display the current roadmap phase status."""

from __future__ import annotations

from pathlib import Path

SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"


def load_roadmap(path: Path) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError("ROADMAP.md not found")
    return path.read_text(encoding="utf-8").splitlines()


def find_phase_indices(lines: list[str]) -> list[int]:
    return [idx for idx, line in enumerate(lines) if line.startswith("## Phase ")]


def find_current_phase_index(phase_indices: list[int], lines: list[str]) -> int | None:
    for idx in phase_indices:
        if "✅" not in lines[idx]:
            return idx
    return phase_indices[-1] if phase_indices else None


def print_current_phase_status(lines: list[str]) -> None:
    phase_indices = find_phase_indices(lines)
    current_idx = find_current_phase_index(phase_indices, lines)

    if current_idx is None:
        print("📊 Current Phase Status: No phases found in ROADMAP.md")
        return

    phase_line = lines[current_idx]
    print(f"📊 Current Phase Status: {phase_line}")
    print(SEPARATOR)

    next_phase_idx = next((idx for idx in phase_indices if idx > current_idx), len(lines))
    section = lines[current_idx + 1 : next_phase_idx]
    # Extract current phase identifier (e.g., "6" or "3.8") for filtering task headings
    phase_identifier = phase_line.split("—", 1)[0].strip().removeprefix("## Phase ").strip()
    task_prefix = f"### Phase {phase_identifier}."
    task_lines = [line for line in section if line.startswith(task_prefix)]

    if not task_lines:
        print("No tasks found for this phase")
    else:
        for line in task_lines:
            print(line)

    print(SEPARATOR)
    print()
    print("Legend: ✅ Complete | 🚧 In Progress | 📋 Planned | ⚠️ Blocked | 🔄 Rework")
    print()
    print("For full details: make roadmap")


def main() -> None:
    lines = load_roadmap(Path("ROADMAP.md"))
    print_current_phase_status(lines)


if __name__ == "__main__":
    main()
