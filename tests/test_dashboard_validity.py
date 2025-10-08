"""Tests for Grafana dashboard JSON validity and structure."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

GRAFANA_DIR = Path(__file__).parent.parent / "deploy" / "grafana"
DASHBOARD_FILES = [
    "system_health.json",
    "trading_activity.json",
    "strategy_performance.json",
    "execution_quality.json",
]


class TestDatasourceConfig:
    """Tests for Prometheus datasource configuration."""

    def test_datasources_yaml_exists(self) -> None:
        """Test datasources.yaml file exists."""
        datasources_path = GRAFANA_DIR / "datasources.yaml"
        assert datasources_path.exists(), "datasources.yaml not found"

    def test_datasources_yaml_valid(self) -> None:
        """Test datasources.yaml is valid YAML."""
        datasources_path = GRAFANA_DIR / "datasources.yaml"
        with open(datasources_path) as f:
            data = yaml.safe_load(f)
        assert data is not None, "datasources.yaml is empty"
        assert "datasources" in data, "Missing 'datasources' key"

    def test_prometheus_datasource_configured(self) -> None:
        """Test Prometheus datasource is configured correctly."""
        datasources_path = GRAFANA_DIR / "datasources.yaml"
        with open(datasources_path) as f:
            data = yaml.safe_load(f)

        datasources = data["datasources"]
        assert isinstance(datasources, list), "datasources must be a list"
        assert len(datasources) > 0, "No datasources configured"

        # Check at least one Prometheus datasource
        prometheus_sources = [ds for ds in datasources if ds.get("type") == "prometheus"]
        assert len(prometheus_sources) > 0, "No Prometheus datasource found"

        # Validate first Prometheus datasource
        prom = prometheus_sources[0]
        assert "name" in prom, "Datasource missing 'name'"
        assert "url" in prom, "Datasource missing 'url'"
        assert prom["type"] == "prometheus", "Datasource type must be 'prometheus'"


class TestDashboardFiles:
    """Tests for Grafana dashboard JSON files."""

    @pytest.mark.parametrize("dashboard_file", DASHBOARD_FILES)
    def test_dashboard_file_exists(self, dashboard_file: str) -> None:
        """Test dashboard file exists."""
        dashboard_path = GRAFANA_DIR / dashboard_file
        assert dashboard_path.exists(), f"{dashboard_file} not found"

    @pytest.mark.parametrize("dashboard_file", DASHBOARD_FILES)
    def test_dashboard_json_valid(self, dashboard_file: str) -> None:
        """Test dashboard is valid JSON."""
        dashboard_path = GRAFANA_DIR / dashboard_file
        with open(dashboard_path) as f:
            data = json.load(f)
        assert data is not None, f"{dashboard_file} is empty"
        assert isinstance(data, dict), f"{dashboard_file} root must be an object"

    @pytest.mark.parametrize("dashboard_file", DASHBOARD_FILES)
    def test_dashboard_required_fields(self, dashboard_file: str) -> None:
        """Test dashboard has required Grafana fields."""
        dashboard_path = GRAFANA_DIR / dashboard_file
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        # Required top-level fields per Grafana schema
        required_fields = [
            "title",
            "panels",
            "schemaVersion",
            "tags",
            "templating",
            "time",
            "timezone",
            "uid",
        ]

        for field in required_fields:
            assert field in dashboard, f"{dashboard_file} missing required field: {field}"

    @pytest.mark.parametrize("dashboard_file", DASHBOARD_FILES)
    def test_dashboard_has_panels(self, dashboard_file: str) -> None:
        """Test dashboard has at least one panel."""
        dashboard_path = GRAFANA_DIR / dashboard_file
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        assert "panels" in dashboard, f"{dashboard_file} missing panels"
        panels = dashboard["panels"]
        assert isinstance(panels, list), f"{dashboard_file} panels must be a list"
        assert len(panels) > 0, f"{dashboard_file} has no panels"

    @pytest.mark.parametrize("dashboard_file", DASHBOARD_FILES)
    def test_dashboard_panels_valid(self, dashboard_file: str) -> None:
        """Test all panels have required structure."""
        dashboard_path = GRAFANA_DIR / dashboard_file
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        panels = dashboard["panels"]
        for idx, panel in enumerate(panels):
            # Required panel fields
            assert "id" in panel, f"{dashboard_file} panel {idx} missing 'id'"
            assert "type" in panel, f"{dashboard_file} panel {idx} missing 'type'"
            assert "title" in panel, f"{dashboard_file} panel {idx} missing 'title'"
            assert "gridPos" in panel, f"{dashboard_file} panel {idx} missing 'gridPos'"
            assert "targets" in panel, f"{dashboard_file} panel {idx} missing 'targets'"

            # Validate gridPos
            grid_pos = panel["gridPos"]
            assert "h" in grid_pos, f"{dashboard_file} panel {idx} gridPos missing 'h'"
            assert "w" in grid_pos, f"{dashboard_file} panel {idx} gridPos missing 'w'"
            assert "x" in grid_pos, f"{dashboard_file} panel {idx} gridPos missing 'x'"
            assert "y" in grid_pos, f"{dashboard_file} panel {idx} gridPos missing 'y'"

    @pytest.mark.parametrize("dashboard_file", DASHBOARD_FILES)
    def test_dashboard_has_prometheus_targets(self, dashboard_file: str) -> None:
        """Test panels have Prometheus query targets."""
        dashboard_path = GRAFANA_DIR / dashboard_file
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        panels = dashboard["panels"]
        for idx, panel in enumerate(panels):
            targets = panel["targets"]
            assert isinstance(targets, list), f"{dashboard_file} panel {idx} targets must be list"
            assert len(targets) > 0, f"{dashboard_file} panel {idx} has no targets"

            for target_idx, target in enumerate(targets):
                assert (
                    "expr" in target
                ), f"{dashboard_file} panel {idx} target {target_idx} missing 'expr'"
                expr = target["expr"]
                assert isinstance(
                    expr, str
                ), f"{dashboard_file} panel {idx} target {target_idx} expr must be string"
                assert (
                    len(expr) > 0
                ), f"{dashboard_file} panel {idx} target {target_idx} expr is empty"


class TestDashboardMetrics:
    """Tests for metric queries in dashboards."""

    def test_system_health_queries_njord_metrics(self) -> None:
        """Test system health dashboard queries njord_ prefixed metrics."""
        dashboard_path = GRAFANA_DIR / "system_health.json"
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        queries = self._extract_queries(dashboard)
        njord_queries = [q for q in queries if "njord_" in q]

        # Should have at least some njord metrics
        # (Some may be generic system metrics without prefix)
        assert len(njord_queries) > 0, "system_health.json should query njord_ metrics"

    def test_trading_activity_uses_implemented_metrics(self) -> None:
        """Test trading activity dashboard uses metrics from Phase 9.2."""
        dashboard_path = GRAFANA_DIR / "trading_activity.json"
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        queries = self._extract_queries(dashboard)

        # These metrics were implemented in Phase 9.2
        implemented_metrics = [
            "njord_orders_placed_total",
            "njord_fills_generated_total",
            "njord_position_size",
            "njord_intents_denied_total",
            "njord_open_orders",
        ]

        for metric in implemented_metrics:
            assert any(metric in q for q in queries), f"trading_activity.json should query {metric}"

    def test_strategy_performance_uses_strategy_metrics(self) -> None:
        """Test strategy performance dashboard uses strategy-specific metrics."""
        dashboard_path = GRAFANA_DIR / "strategy_performance.json"
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        queries = self._extract_queries(dashboard)

        # These metrics are strategy-related
        strategy_metrics = [
            "njord_signals_generated_total",
            "njord_strategy_errors_total",
            "njord_signal_generation_duration_seconds",
        ]

        for metric in strategy_metrics:
            assert any(
                metric in q for q in queries
            ), f"strategy_performance.json should query {metric}"

    def test_execution_quality_uses_execution_metrics(self) -> None:
        """Test execution quality dashboard uses execution-related metrics."""
        dashboard_path = GRAFANA_DIR / "execution_quality.json"
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        queries = self._extract_queries(dashboard)

        # These metrics are execution-related (some from Phase 9.2, others planned)
        execution_metrics = [
            "njord_fills_generated_total",
            "njord_orders_placed_total",
            "njord_fill_price_deviation_bps",
            "njord_risk_check_duration_seconds",
        ]

        found_count = sum(1 for metric in execution_metrics if any(metric in q for q in queries))
        assert found_count >= 2, "execution_quality.json should query at least 2 execution metrics"

    def _extract_queries(self, dashboard: dict[str, Any]) -> list[str]:
        """Extract all PromQL queries from dashboard."""
        queries = []
        for panel in dashboard.get("panels", []):
            for target in panel.get("targets", []):
                expr = target.get("expr")
                if expr:
                    queries.append(expr)
        return queries


class TestDashboardVariables:
    """Tests for dashboard template variables."""

    @pytest.mark.parametrize("dashboard_file", DASHBOARD_FILES)
    def test_dashboard_has_templating(self, dashboard_file: str) -> None:
        """Test dashboard has templating configuration."""
        dashboard_path = GRAFANA_DIR / dashboard_file
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        assert "templating" in dashboard, f"{dashboard_file} missing templating"
        templating = dashboard["templating"]
        assert "list" in templating, f"{dashboard_file} templating missing list"

    def test_trading_activity_has_expected_variables(self) -> None:
        """Test trading activity dashboard has strategy/symbol/venue variables."""
        dashboard_path = GRAFANA_DIR / "trading_activity.json"
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        variables = {var["name"] for var in dashboard["templating"]["list"]}

        expected_vars = {"strategy", "symbol", "venue"}
        assert expected_vars.issubset(
            variables
        ), f"trading_activity.json missing variables: {expected_vars - variables}"

    def test_strategy_performance_has_strategy_variable(self) -> None:
        """Test strategy performance dashboard has strategy variable."""
        dashboard_path = GRAFANA_DIR / "strategy_performance.json"
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        variables = {var["name"] for var in dashboard["templating"]["list"]}
        assert "strategy" in variables, "strategy_performance.json missing 'strategy' variable"


class TestDashboardRefresh:
    """Tests for dashboard auto-refresh configuration."""

    @pytest.mark.parametrize("dashboard_file", DASHBOARD_FILES)
    def test_dashboard_has_auto_refresh(self, dashboard_file: str) -> None:
        """Test dashboard has auto-refresh configured."""
        dashboard_path = GRAFANA_DIR / dashboard_file
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        assert "refresh" in dashboard, f"{dashboard_file} missing refresh setting"
        refresh = dashboard["refresh"]

        # Should be set to 5s or similar interval
        assert refresh in [
            "5s",
            "10s",
            "30s",
            "1m",
        ], f"{dashboard_file} refresh should be short interval"


class TestReadmeFile:
    """Tests for README.md documentation."""

    def test_readme_exists(self) -> None:
        """Test README.md exists in grafana directory."""
        readme_path = GRAFANA_DIR / "README.md"
        assert readme_path.exists(), "README.md not found"

    def test_readme_has_content(self) -> None:
        """Test README.md is not empty."""
        readme_path = GRAFANA_DIR / "README.md"
        content = readme_path.read_text()
        assert len(content) > 100, "README.md seems too short"

    def test_readme_documents_all_dashboards(self) -> None:
        """Test README.md documents all dashboard files."""
        readme_path = GRAFANA_DIR / "README.md"
        content = readme_path.read_text()

        for dashboard_file in DASHBOARD_FILES:
            dashboard_name = dashboard_file.replace(".json", "")
            assert dashboard_name in content, f"README.md does not mention {dashboard_file}"

    def test_readme_has_setup_instructions(self) -> None:
        """Test README.md contains setup instructions."""
        readme_path = GRAFANA_DIR / "README.md"
        content = readme_path.read_text()

        # Check for key sections
        required_sections = [
            "Setup Instructions",
            "Prometheus",
            "Grafana",
            "Import",
        ]

        for section in required_sections:
            assert section in content, f"README.md missing section: {section}"


class TestDashboardTags:
    """Tests for dashboard tagging."""

    @pytest.mark.parametrize("dashboard_file", DASHBOARD_FILES)
    def test_dashboard_has_njord_tag(self, dashboard_file: str) -> None:
        """Test dashboard is tagged with 'njord'."""
        dashboard_path = GRAFANA_DIR / dashboard_file
        with open(dashboard_path) as f:
            dashboard = json.load(f)

        tags = dashboard.get("tags", [])
        assert "njord" in tags, f"{dashboard_file} should be tagged with 'njord'"

    def test_dashboards_have_unique_uids(self) -> None:
        """Test each dashboard has a unique UID."""
        uids = []
        for dashboard_file in DASHBOARD_FILES:
            dashboard_path = GRAFANA_DIR / dashboard_file
            with open(dashboard_path) as f:
                dashboard = json.load(f)
            uid = dashboard.get("uid")
            assert uid is not None, f"{dashboard_file} missing uid"
            uids.append(uid)

        assert len(uids) == len(set(uids)), "Dashboard UIDs are not unique"
