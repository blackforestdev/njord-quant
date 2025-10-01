"""Utility to display roadmap progress and next planned task."""

from __future__ import annotations

from pathlib import Path

SEPARATOR = "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"


def load_roadmap(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError("ROADMAP.md not found")
    return path.read_text(encoding="utf-8")


def print_phase_progress(roadmap_text: str) -> None:
    phase_lines = [
        line.rstrip() for line in roadmap_text.splitlines() if line.startswith("## Phase ")
    ]
    print("📈 Phase Progress:")
    if phase_lines:
        for line in phase_lines:
            print(f"  {line}")
    else:
        print("  No phases found in ROADMAP.md")


def print_next_planned_task(roadmap_text: str) -> None:
    print("\n🎯 Next Planned Task:")
    print(SEPARATOR)

    lines = roadmap_text.splitlines()
    phase_indices = [idx for idx, line in enumerate(lines) if line.startswith("## Phase ")]
    planned_indices = [idx for idx in phase_indices if "📋" in lines[idx]]

    if not planned_indices:
        print("No planned tasks found")
        print(SEPARATOR)
        return

    start = planned_indices[0]
    next_indices = [idx for idx in phase_indices if idx > start]
    end = next_indices[0] if next_indices else len(lines)

    section = lines[start:end]

    heading_indices = [idx for idx, line in enumerate(section) if line.startswith("### ")]
    summary_end = heading_indices[0] if heading_indices else len(section)
    summary_lines = section[:summary_end]

    incomplete_heading_idx: int | None = None
    for idx in heading_indices:
        if "✅" not in section[idx]:
            incomplete_heading_idx = idx
            break

    display_lines: list[str] = list(summary_lines)

    if incomplete_heading_idx is not None:
        next_heading = next(
            (idx for idx in heading_indices if idx > incomplete_heading_idx), len(section)
        )
        display_lines.extend(section[incomplete_heading_idx:next_heading])
    else:
        if summary_end < len(section):
            display_lines.extend(section[summary_end:])
        display_lines.append("(All tasks in this phase are marked complete.)")

    # Collapse consecutive blank lines for cleaner output
    cleaned_lines: list[str] = []
    for line in display_lines:
        if cleaned_lines and not line.strip() and not cleaned_lines[-1].strip():
            continue
        cleaned_lines.append(line)

    max_lines = 40
    if len(cleaned_lines) > max_lines:
        preview = "\n".join(cleaned_lines[:max_lines])
        print(preview)
        print("... (see ROADMAP.md for full details)")
    else:
        print("\n".join(cleaned_lines).strip())
    print(SEPARATOR)


def main() -> None:
    roadmap_text = load_roadmap(Path("ROADMAP.md"))
    print("**Status Tracking:** ✅ Complete | 🚧 In Progress | 📋 Planned")
    print()
    print_phase_progress(roadmap_text)
    print_next_planned_task(roadmap_text)


if __name__ == "__main__":
    main()
