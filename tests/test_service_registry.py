"""Tests for service registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from controller.metadata import ServiceMetadata
from controller.registry import ServiceRegistry


class TestServiceMetadata:
    """Tests for ServiceMetadata contract."""

    def test_creates_valid_service_metadata(self, tmp_path: Path) -> None:
        """Test creating valid ServiceMetadata."""
        service_dir = tmp_path / "test_service"
        service_dir.mkdir()

        metadata = ServiceMetadata(
            name="test_service",
            entry_point="apps.test_service",
            directory=service_dir,
            dependencies=["risk_engine"],
            groups=["live", "paper"],
        )

        assert metadata.name == "test_service"
        assert metadata.entry_point == "apps.test_service"
        assert metadata.directory == service_dir
        assert metadata.dependencies == ["risk_engine"]
        assert metadata.groups == ["live", "paper"]

    def test_allows_empty_dependencies_and_groups(self, tmp_path: Path) -> None:
        """Test ServiceMetadata allows empty dependencies and groups."""
        service_dir = tmp_path / "test_service"
        service_dir.mkdir()

        metadata = ServiceMetadata(
            name="test_service",
            entry_point="apps.test_service",
            directory=service_dir,
            dependencies=[],
            groups=[],
        )

        assert metadata.dependencies == []
        assert metadata.groups == []

    def test_rejects_empty_name(self, tmp_path: Path) -> None:
        """Test ServiceMetadata rejects empty name."""
        service_dir = tmp_path / "test_service"
        service_dir.mkdir()

        with pytest.raises(ValueError, match="name must not be empty"):
            ServiceMetadata(
                name="",
                entry_point="apps.test_service",
                directory=service_dir,
                dependencies=[],
                groups=[],
            )

    def test_rejects_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test ServiceMetadata rejects nonexistent directory."""
        nonexistent = tmp_path / "nonexistent"

        with pytest.raises(ValueError, match="does not exist"):
            ServiceMetadata(
                name="test",
                entry_point="apps.test",
                directory=nonexistent,
                dependencies=[],
                groups=[],
            )

    def test_rejects_file_as_directory(self, tmp_path: Path) -> None:
        """Test ServiceMetadata rejects file path as directory."""
        file_path = tmp_path / "test_file"
        file_path.touch()

        with pytest.raises(ValueError, match="is not a directory"):
            ServiceMetadata(
                name="test",
                entry_point="apps.test",
                directory=file_path,
                dependencies=[],
                groups=[],
            )

    def test_immutable(self, tmp_path: Path) -> None:
        """Test ServiceMetadata is immutable."""
        service_dir = tmp_path / "test_service"
        service_dir.mkdir()

        metadata = ServiceMetadata(
            name="test",
            entry_point="apps.test",
            directory=service_dir,
            dependencies=[],
            groups=[],
        )

        with pytest.raises(AttributeError):
            metadata.name = "changed"  # type: ignore[misc]


class TestServiceRegistry:
    """Tests for ServiceRegistry."""

    def test_initializes_with_default_apps_dir(self) -> None:
        """Test ServiceRegistry initializes with default apps/ directory."""
        registry = ServiceRegistry()

        assert registry.apps_dir == Path("apps")
        # Should discover real services in apps/ directory
        assert len(registry.services) > 0

    def test_initializes_with_custom_apps_dir(self, tmp_path: Path) -> None:
        """Test ServiceRegistry initializes with custom apps directory."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        registry = ServiceRegistry(apps_dir=apps_dir)

        assert registry.apps_dir == apps_dir
        assert len(registry.services) == 0  # Empty directory

    def test_discovers_services_in_directory(self, tmp_path: Path) -> None:
        """Test ServiceRegistry discovers services with __main__.py."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        # Create valid service directories
        for service_name in ["service1", "service2", "service3"]:
            service_dir = apps_dir / service_name
            service_dir.mkdir()
            (service_dir / "__main__.py").touch()

        registry = ServiceRegistry(apps_dir=apps_dir)

        assert len(registry.services) == 3
        assert "service1" in registry.services
        assert "service2" in registry.services
        assert "service3" in registry.services

    def test_skips_directories_without_main(self, tmp_path: Path) -> None:
        """Test ServiceRegistry skips directories without __main__.py."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        # Create directory without __main__.py
        (apps_dir / "not_a_service").mkdir()

        # Create valid service
        service_dir = apps_dir / "valid_service"
        service_dir.mkdir()
        (service_dir / "__main__.py").touch()

        registry = ServiceRegistry(apps_dir=apps_dir)

        assert len(registry.services) == 1
        assert "valid_service" in registry.services
        assert "not_a_service" not in registry.services

    def test_skips_special_directories(self, tmp_path: Path) -> None:
        """Test ServiceRegistry skips .dot and __pycache__ directories."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        # Create special directories
        for name in [".hidden", "__pycache__"]:
            special_dir = apps_dir / name
            special_dir.mkdir()
            (special_dir / "__main__.py").touch()

        # Create valid service
        service_dir = apps_dir / "valid_service"
        service_dir.mkdir()
        (service_dir / "__main__.py").touch()

        registry = ServiceRegistry(apps_dir=apps_dir)

        assert len(registry.services) == 1
        assert "valid_service" in registry.services
        assert ".hidden" not in registry.services
        assert "__pycache__" not in registry.services

    def test_builds_correct_entry_points(self, tmp_path: Path) -> None:
        """Test ServiceRegistry builds correct Python module entry points."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        service_dir = apps_dir / "my_service"
        service_dir.mkdir()
        (service_dir / "__main__.py").touch()

        registry = ServiceRegistry(apps_dir=apps_dir)

        metadata = registry.get_service("my_service")
        assert metadata.entry_point == "apps.my_service"

    def test_get_service_returns_metadata(self) -> None:
        """Test get_service returns ServiceMetadata."""
        registry = ServiceRegistry()

        # Should have at least risk_engine in real apps/
        metadata = registry.get_service("risk_engine")

        assert isinstance(metadata, ServiceMetadata)
        assert metadata.name == "risk_engine"
        assert metadata.entry_point == "apps.risk_engine"

    def test_get_service_raises_keyerror_for_missing(self) -> None:
        """Test get_service raises KeyError for missing service."""
        registry = ServiceRegistry()

        with pytest.raises(KeyError, match="Service 'nonexistent' not found"):
            registry.get_service("nonexistent")

    def test_get_start_order_simple(self, tmp_path: Path) -> None:
        """Test get_start_order with simple dependency chain."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        # Create services: a -> b -> c
        for name in ["service_a", "service_b", "service_c"]:
            service_dir = apps_dir / name
            service_dir.mkdir()
            (service_dir / "__main__.py").touch()

        registry = ServiceRegistry(apps_dir=apps_dir)

        # Manually set dependencies for testing
        registry.services["service_b"].dependencies.append("service_a")
        registry.services["service_c"].dependencies.append("service_b")

        order = registry.get_start_order(["service_a", "service_b", "service_c"])

        assert order.index("service_a") < order.index("service_b")
        assert order.index("service_b") < order.index("service_c")

    def test_get_start_order_no_dependencies(self, tmp_path: Path) -> None:
        """Test get_start_order with no dependencies returns sorted order."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        for name in ["service_c", "service_a", "service_b"]:
            service_dir = apps_dir / name
            service_dir.mkdir()
            (service_dir / "__main__.py").touch()

        registry = ServiceRegistry(apps_dir=apps_dir)

        order = registry.get_start_order(["service_c", "service_a", "service_b"])

        # Should be alphabetically sorted when no dependencies
        assert order == ["service_a", "service_b", "service_c"]

    def test_get_start_order_partial_dependencies(self, tmp_path: Path) -> None:
        """Test get_start_order with partial dependency graph."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        for name in ["a", "b", "c", "d"]:
            service_dir = apps_dir / name
            service_dir.mkdir()
            (service_dir / "__main__.py").touch()

        registry = ServiceRegistry(apps_dir=apps_dir)

        # Set up dependencies: b->a, d->c, a and c have no deps
        registry.services["b"].dependencies.append("a")
        registry.services["d"].dependencies.append("c")

        order = registry.get_start_order(["a", "b", "c", "d"])

        # a must come before b, c must come before d
        assert order.index("a") < order.index("b")
        assert order.index("c") < order.index("d")

    def test_get_start_order_raises_for_missing_service(self, tmp_path: Path) -> None:
        """Test get_start_order raises KeyError for missing service."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        service_dir = apps_dir / "service_a"
        service_dir.mkdir()
        (service_dir / "__main__.py").touch()

        registry = ServiceRegistry(apps_dir=apps_dir)

        with pytest.raises(KeyError, match="Service 'nonexistent' not found"):
            registry.get_start_order(["service_a", "nonexistent"])

    def test_get_start_order_handles_circular_dependency(self, tmp_path: Path) -> None:
        """Test get_start_order detects circular dependencies."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        for name in ["a", "b"]:
            service_dir = apps_dir / name
            service_dir.mkdir()
            (service_dir / "__main__.py").touch()

        registry = ServiceRegistry(apps_dir=apps_dir)

        # Create circular dependency: a->b, b->a
        registry.services["a"].dependencies.append("b")
        registry.services["b"].dependencies.append("a")

        with pytest.raises(ValueError, match="Circular dependency detected"):
            registry.get_start_order(["a", "b"])

    def test_get_service_group_live(self) -> None:
        """Test get_service_group returns live services."""
        registry = ServiceRegistry()

        live_services = registry.get_service_group("live")

        assert "md_ingest" in live_services
        assert "risk_engine" in live_services
        assert "broker_binanceus" in live_services

    def test_get_service_group_paper(self) -> None:
        """Test get_service_group returns paper trading services."""
        registry = ServiceRegistry()

        paper_services = registry.get_service_group("paper")

        assert "md_ingest" in paper_services
        assert "risk_engine" in paper_services
        assert "paper_trader" in paper_services

    def test_get_service_group_backtest(self) -> None:
        """Test get_service_group returns empty list for backtest."""
        registry = ServiceRegistry()

        backtest_services = registry.get_service_group("backtest")

        assert backtest_services == []

    def test_get_service_group_all(self) -> None:
        """Test get_service_group('all') returns all discovered services."""
        registry = ServiceRegistry()

        all_services = registry.get_service_group("all")

        assert len(all_services) > 0
        assert "risk_engine" in all_services
        assert "paper_trader" in all_services
        # Should be sorted
        assert all_services == sorted(all_services)

    def test_get_service_group_filters_undiscovered_services(self, tmp_path: Path) -> None:
        """Test get_service_group only returns discovered services."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        # Only create md_ingest service
        service_dir = apps_dir / "md_ingest"
        service_dir.mkdir()
        (service_dir / "__main__.py").touch()

        registry = ServiceRegistry(apps_dir=apps_dir)

        live_services = registry.get_service_group("live")

        # Should only contain md_ingest (the only discovered service in 'live' group)
        assert live_services == ["md_ingest"]

    def test_list_services_returns_all_discovered(self) -> None:
        """Test list_services returns all discovered services."""
        registry = ServiceRegistry()

        services = registry.list_services()

        assert isinstance(services, dict)
        assert len(services) > 0
        assert "risk_engine" in services
        assert isinstance(services["risk_engine"], ServiceMetadata)

    def test_handles_nonexistent_apps_directory_gracefully(self, tmp_path: Path) -> None:
        """Test ServiceRegistry handles nonexistent apps directory."""
        nonexistent = tmp_path / "nonexistent"

        registry = ServiceRegistry(apps_dir=nonexistent)

        assert registry.apps_dir == nonexistent
        assert len(registry.services) == 0
        assert registry.list_services() == {}

    def test_real_services_have_correct_dependencies(self) -> None:
        """Test real services in apps/ have correct dependency ordering."""
        registry = ServiceRegistry()

        # paper_trader should depend on risk_engine
        if "paper_trader" in registry.services:
            paper_trader = registry.get_service("paper_trader")
            assert "risk_engine" in paper_trader.dependencies

        # broker should depend on risk_engine
        if "broker_binanceus" in registry.services:
            broker = registry.get_service("broker_binanceus")
            assert "risk_engine" in broker.dependencies

    def test_real_services_start_order_respects_dependencies(self) -> None:
        """Test real services can be ordered by dependencies."""
        registry = ServiceRegistry()

        # Get all discovered services
        all_services = list(registry.services.keys())

        if len(all_services) > 0:
            # Should not raise
            order = registry.get_start_order(all_services)

            # Verify order respects known dependencies
            if "risk_engine" in order and "paper_trader" in order:
                assert order.index("risk_engine") < order.index("paper_trader")

            if "risk_engine" in order and "broker_binanceus" in order:
                assert order.index("risk_engine") < order.index("broker_binanceus")

            if "md_ingest" in order and "ohlcv_aggregator" in order:
                assert order.index("md_ingest") < order.index("ohlcv_aggregator")
