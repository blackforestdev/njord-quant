"""Tests for telemetry documentation validity."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS_DIR = Path(__file__).parent.parent / "docs" / "telemetry"
ROOT_DIR = Path(__file__).parent.parent


class TestTelemetryDocs:
    """Tests for telemetry documentation files."""

    def test_all_docs_exist(self) -> None:
        """Test all required documentation files exist."""
        required_docs = [
            "metrics_catalog.md",
            "grafana_setup.md",
            "operations_runbook.md",
            "api_reference.md",
        ]

        for doc in required_docs:
            doc_path = DOCS_DIR / doc
            assert doc_path.exists(), f"Missing documentation: {doc}"

    def test_docs_not_empty(self) -> None:
        """Test documentation files are not empty."""
        for doc_file in DOCS_DIR.glob("*.md"):
            content = doc_file.read_text()
            assert len(content) > 0, f"{doc_file.name} is empty"
            assert len(content) > 100, f"{doc_file.name} is too short (< 100 chars)"

    def test_docs_have_headers(self) -> None:
        """Test documentation files have proper headers."""
        for doc_file in DOCS_DIR.glob("*.md"):
            content = doc_file.read_text()
            # Check for H1 header
            assert content.startswith("#"), f"{doc_file.name} missing H1 header"

            # Check for table of contents
            assert (
                "## Table of Contents" in content or "## " in content
            ), f"{doc_file.name} missing table of contents or sections"

    def test_internal_links_valid(self) -> None:
        """Test internal documentation links are valid."""
        # Pattern for markdown links: [text](path)
        link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

        for doc_file in DOCS_DIR.glob("*.md"):
            content = doc_file.read_text()

            for match in link_pattern.finditer(content):
                link_text = match.group(1)
                link_path = match.group(2)

                # Skip external links (http/https)
                if link_path.startswith(("http://", "https://")):
                    continue

                # Skip anchors (same-page links)
                if link_path.startswith("#"):
                    continue

                # Strip anchor from path (e.g., "file.md#section" -> "file.md")
                path_without_anchor = link_path.split("#")[0]

                # Skip if only anchor remains (already handled above)
                if not path_without_anchor:
                    continue

                # Resolve relative path
                if path_without_anchor.startswith("./"):
                    resolved = (doc_file.parent / path_without_anchor).resolve()
                else:
                    resolved = (doc_file.parent / path_without_anchor).resolve()

                assert (
                    resolved.exists()
                ), f"Broken link in {doc_file.name}: [{link_text}]({link_path}) -> {resolved}"

    def test_code_blocks_properly_formatted(self) -> None:
        """Test code blocks are properly formatted."""
        for doc_file in DOCS_DIR.glob("*.md"):
            content = doc_file.read_text()
            lines = content.split("\n")

            in_code_block = False
            code_block_line = 0

            for i, line in enumerate(lines, 1):
                if line.strip().startswith("```"):
                    if not in_code_block:
                        in_code_block = True
                        code_block_line = i
                    else:
                        in_code_block = False

            # Ensure all code blocks are closed
            assert (
                not in_code_block
            ), f"{doc_file.name} has unclosed code block starting at line {code_block_line}"

    def test_referenced_files_exist(self) -> None:
        """Test referenced configuration and script files exist."""
        # Check metrics_catalog.md references
        catalog = DOCS_DIR / "metrics_catalog.md"
        content = catalog.read_text()

        # No specific files referenced in metrics catalog currently

        # Check grafana_setup.md references
        setup = DOCS_DIR / "grafana_setup.md"
        content = setup.read_text()

        # Check for docker-compose reference
        assert "docker-compose.telemetry.yml" in content

        # Check operations_runbook.md references
        runbook = DOCS_DIR / "operations_runbook.md"
        content = runbook.read_text()

        # Check for scripts/metrics_cleanup.py reference
        assert "scripts/metrics_cleanup.py" in content
        cleanup_script = ROOT_DIR / "scripts" / "metrics_cleanup.py"
        assert cleanup_script.exists(), "scripts/metrics_cleanup.py not found"

    def test_metrics_catalog_completeness(self) -> None:
        """Test metrics catalog documents key metrics."""
        catalog = DOCS_DIR / "metrics_catalog.md"
        content = catalog.read_text()

        # Check for key metric categories
        required_sections = [
            "Strategy Metrics",
            "Portfolio Metrics",
            "Risk Metrics",
            "Order Execution Metrics",
            "System Health Metrics",
        ]

        for section in required_sections:
            assert f"## {section}" in content, f"Missing section: {section}"

        # Check for key metrics
        key_metrics = [
            "njord_strategy_pnl_usd",
            "njord_orders_placed_total",
            "njord_event_loop_lag_seconds",
            "njord_memory_usage_mb",
        ]

        for metric in key_metrics:
            assert metric in content, f"Missing metric documentation: {metric}"

        # Check for PromQL examples
        assert "```promql" in content, "Missing PromQL examples"

        # Check for alert examples
        assert "alert:" in content.lower() or "Alert" in content, "Missing alert examples"

    def test_grafana_setup_has_instructions(self) -> None:
        """Test Grafana setup guide has all required sections."""
        setup = DOCS_DIR / "grafana_setup.md"
        content = setup.read_text()

        required_sections = [
            "Prometheus Installation",
            "Grafana Installation",
            "Datasource Configuration",
            "Dashboard Import",
            "Verification",
        ]

        for section in required_sections:
            assert section in content, f"Missing section: {section}"

        # Check for docker-compose example
        assert "docker-compose" in content, "Missing docker-compose instructions"

        # Check for curl commands (verification steps)
        assert "curl" in content, "Missing verification curl commands"

    def test_operations_runbook_has_procedures(self) -> None:
        """Test operations runbook has all required procedures."""
        runbook = DOCS_DIR / "operations_runbook.md"
        content = runbook.read_text()

        required_sections = [
            "Service Management",
            "Metrics Retention Management",
            "Troubleshooting",
            "Performance Tuning",
            "Maintenance Procedures",
        ]

        for section in required_sections:
            assert section in content, f"Missing section: {section}"

        # Check for code examples
        assert "```bash" in content, "Missing bash command examples"

        # Check for troubleshooting scenarios
        assert (
            "Symptoms:" in content or "Solutions:" in content
        ), "Missing troubleshooting symptoms/solutions"

    def test_api_reference_has_examples(self) -> None:
        """Test API reference has code examples."""
        api_ref = DOCS_DIR / "api_reference.md"
        content = api_ref.read_text()

        # Check for key API sections
        required_sections = [
            "Contracts",
            "Metric Registry",
            "Prometheus Exporter",
            "Alert Manager",
            "Metrics Retention",
        ]

        for section in required_sections:
            assert section in content, f"Missing section: {section}"

        # Check for Python code examples
        assert "```python" in content, "Missing Python code examples"

        # Check for imports
        assert "from telemetry" in content, "Missing telemetry imports"

        # Check for complete example
        assert "Complete Example" in content or "Full" in content, "Missing complete example"

    def test_cross_references_valid(self) -> None:
        """Test cross-references between docs are valid."""
        # Metrics catalog should reference other docs
        catalog = DOCS_DIR / "metrics_catalog.md"
        content = catalog.read_text()

        # Should link to grafana_setup.md
        assert "grafana_setup.md" in content or "Grafana Setup" in content

        # API reference should reference other docs
        api_ref = DOCS_DIR / "api_reference.md"
        content = api_ref.read_text()

        # Should link to metrics catalog
        assert "metrics_catalog.md" in content or "Metrics Catalog" in content

    def test_no_placeholder_text(self) -> None:
        """Test documentation has no placeholder text."""
        placeholders = ["TODO", "TBD", "FIXME", "XXX", "[TBD]"]

        for doc_file in DOCS_DIR.glob("*.md"):
            content = doc_file.read_text()

            for placeholder in placeholders:
                # Allow [TBD] in specific contexts (emergency contacts)
                if placeholder == "[TBD]" and "Emergency Contacts" in content:
                    continue

                # Check if placeholder exists outside code blocks
                lines = content.split("\n")
                in_code_block = False

                for line in lines:
                    if line.strip().startswith("```"):
                        in_code_block = not in_code_block
                        continue

                    if (
                        not in_code_block
                        and placeholder in line
                        and "Emergency Contacts" not in content[: content.index(line)]
                    ):
                        pytest.fail(f"Found placeholder '{placeholder}' in {doc_file.name}: {line}")

    def test_yaml_examples_valid(self) -> None:
        """Test YAML examples in documentation are valid."""
        import yaml as yaml_lib

        for doc_file in DOCS_DIR.glob("*.md"):
            content = doc_file.read_text()
            lines = content.split("\n")

            in_yaml_block = False
            yaml_content: list[str] = []
            yaml_start_line = 0

            for i, line in enumerate(lines, 1):
                if line.strip().startswith("```yaml"):
                    in_yaml_block = True
                    yaml_start_line = i
                    yaml_content = []
                elif line.strip().startswith("```") and in_yaml_block:
                    # End of YAML block, validate it
                    if yaml_content:
                        yaml_text = "\n".join(yaml_content)
                        try:
                            yaml_lib.safe_load(yaml_text)
                        except yaml_lib.YAMLError as e:
                            pytest.fail(
                                f"Invalid YAML in {doc_file.name} at line {yaml_start_line}: {e}"
                            )
                    in_yaml_block = False
                elif in_yaml_block:
                    yaml_content.append(line)

    def test_docs_have_last_updated(self) -> None:
        """Test documentation files have last updated date."""
        for doc_file in DOCS_DIR.glob("*.md"):
            content = doc_file.read_text()

            # Check for last updated marker
            assert (
                "Last Updated:" in content
                or "**Last Updated:**" in content
                or "last updated" in content.lower()
            ), f"{doc_file.name} missing last updated date"

    def test_prometheus_metric_names_valid(self) -> None:
        """Test Prometheus metric names follow conventions."""
        catalog = DOCS_DIR / "metrics_catalog.md"
        content = catalog.read_text()

        # Extract metric names (lines starting with ###)
        metric_pattern = re.compile(r"### `(njord_\w+)`")

        for match in metric_pattern.finditer(content):
            metric_name = match.group(1)

            # Check naming conventions
            assert metric_name.startswith("njord_"), f"Metric {metric_name} missing njord_ prefix"

            # Check for proper suffixes
            if "_total" in metric_name:
                assert metric_name.endswith(
                    "_total"
                ), f"Counter {metric_name} should end with _total"

            # Should be snake_case
            assert metric_name == metric_name.lower(), f"Metric {metric_name} should be lowercase"
            assert "-" not in metric_name, f"Metric {metric_name} should use underscore, not dash"
