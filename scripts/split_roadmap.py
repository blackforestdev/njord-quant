"""Split monolithic ROADMAP.md into hierarchical phase files."""

from __future__ import annotations

from pathlib import Path


def extract_phase_slug(phase_line: str) -> str:
    """Extract slug from phase title for filename.

    Example: "## Phase 13 — Advanced Strategy Toolkit 📋"
    Returns: "strategies"
    """
    if "—" not in phase_line:
        return "phase"

    title_part = phase_line.split("—", 1)[1]
    # Remove status emoji and extract first significant word
    title_clean = title_part.replace("✅", "").replace("🚧", "").replace("📋", "").strip()

    # Map to concise slug
    slug_map = {
        "Bootstrap": "bootstrap",
        "Event Bus": "event-bus",
        "Risk Engine": "risk-paper",
        "Market Data Storage": "market-data",
        "Backtester": "backtester",
        "Portfolio": "portfolio",
        "Research API": "research-api",
        "Execution Layer": "execution",
        "Metrics": "telemetry",
        "Telemetry": "telemetry",
        "Live Trade Controller": "controller",
        "Monitoring": "monitoring",
        "Compliance": "compliance",
        "Advanced Strategy": "strategies",
        "Simulation": "simulation",
        "Deployment": "deployment",
        "Optimization": "optimization",
    }

    for key, slug in slug_map.items():
        if key in title_clean:
            return slug

    # Fallback: use first word
    return title_clean.split()[0].lower().replace(" ", "-")


def split_roadmap() -> None:
    """Split ROADMAP.md into phase files."""
    roadmap_path = Path("roadmap/archive/ROADMAP-monolith.md")
    if not roadmap_path.exists():
        print(f"Error: {roadmap_path} not found")
        return

    roadmap = roadmap_path.read_text(encoding="utf-8")
    lines = roadmap.splitlines()

    # Find all phase headers (## Phase X)
    phase_indices = [
        idx
        for idx, line in enumerate(lines)
        if line.startswith("## Phase ") and not line.startswith("## Phases 13-16")
    ]

    print(f"Found {len(phase_indices)} phase sections")

    output_dir = Path("roadmap/phases")
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, start_idx in enumerate(phase_indices):
        phase_line = lines[start_idx]

        # Extract phase number
        phase_num_str = phase_line.split("—")[0].replace("## Phase", "").strip()
        try:
            phase_num = int(phase_num_str.split(".")[0])
        except ValueError:
            print(f"Skipping invalid phase line: {phase_line}")
            continue

        # Extract slug
        slug = extract_phase_slug(phase_line)

        # Find end of this phase (next phase header or special marker)
        end_idx = len(lines)
        if i + 1 < len(phase_indices):
            end_idx = phase_indices[i + 1]
        else:
            # Look for "## Dependencies Summary" or "## Phases 13-16" or "## Appendix"
            for idx in range(start_idx + 1, len(lines)):
                if lines[idx].startswith("## Dependencies Summary"):
                    end_idx = idx
                    break
                if lines[idx].startswith("## Phases 13-16"):
                    end_idx = idx
                    break
                if lines[idx].startswith("## Appendix"):
                    end_idx = idx
                    break

        # Extract content
        phase_content = "\n".join(lines[start_idx:end_idx]).rstrip() + "\n"

        # Write to file
        output_file = output_dir / f"phase-{phase_num:02d}-{slug}.md"
        output_file.write_text(phase_content, encoding="utf-8")
        line_count = len(phase_content.splitlines())
        print(f"Created: {output_file} ({line_count} lines)")


if __name__ == "__main__":
    split_roadmap()
