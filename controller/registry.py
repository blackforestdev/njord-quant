"""Service registry for discovering and managing njord services."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from controller.metadata import ServiceGroup, ServiceMetadata

# Service dependency mapping (what each service depends on)
SERVICE_DEPENDENCIES: dict[str, list[str]] = {
    "md_ingest": [],
    "risk_engine": [],
    "paper_trader": ["risk_engine"],
    "broker_binanceus": ["risk_engine"],
    "portfolio_manager": ["risk_engine"],
    "strategy_runner": ["risk_engine"],
    "ohlcv_aggregator": ["md_ingest"],
    "replay_engine": [],
    "metric_aggregator": [],
    "metrics_dashboard": ["metric_aggregator"],
    "monitor": [],
    "portfolio_accounting": [],
}

# Service group definitions
# Note: Only includes services that have __main__.py entry points
SERVICE_GROUPS: dict[ServiceGroup, list[str]] = {
    "live": [
        "md_ingest",
        "risk_engine",
        "broker_binanceus",
        # Note: portfolio_manager and metric_aggregator not yet implemented
    ],
    "paper": [
        "md_ingest",
        "risk_engine",
        "paper_trader",
        # Note: portfolio_manager and metric_aggregator not yet implemented
    ],
    "backtest": [],  # No persistent services for backtest
    "all": [],  # Dynamically populated with all services
}


class ServiceRegistry:
    """Registry for discovering and managing njord services.

    Attributes:
        apps_dir: Directory containing service packages
        services: Discovered services mapped by name
    """

    def __init__(self, apps_dir: Path = Path("apps")) -> None:
        """Initialize service registry.

        Args:
            apps_dir: Directory containing service packages
        """
        self.apps_dir = apps_dir
        self.services: dict[str, ServiceMetadata] = {}
        if apps_dir.exists():
            self.services = self.discover_services()

    def discover_services(self) -> dict[str, ServiceMetadata]:
        """Discover all services in apps/ directory.

        Scans the apps directory for service packages (directories with __main__.py)
        and builds metadata for each discovered service.

        Returns:
            Dict mapping service name to metadata
        """
        services: dict[str, ServiceMetadata] = {}

        if not self.apps_dir.exists():
            return services

        for service_dir in sorted(self.apps_dir.iterdir()):
            # Skip non-directories and special directories
            if not service_dir.is_dir():
                continue
            if service_dir.name.startswith(".") or service_dir.name == "__pycache__":
                continue

            # Check for __main__.py to identify valid service
            main_file = service_dir / "__main__.py"
            if not main_file.exists():
                continue

            service_name = service_dir.name
            entry_point = f"apps.{service_name}"
            dependencies = SERVICE_DEPENDENCIES.get(service_name, [])

            # Determine which groups this service belongs to
            groups: list[ServiceGroup] = []
            for group_name, group_services in SERVICE_GROUPS.items():
                if group_name == "all":
                    continue
                if service_name in group_services:
                    groups.append(group_name)

            metadata = ServiceMetadata(
                name=service_name,
                entry_point=entry_point,
                directory=service_dir.resolve(),
                dependencies=dependencies,
                groups=groups,
            )
            services[service_name] = metadata

        return services

    def get_service(self, name: str) -> ServiceMetadata:
        """Get service metadata by name.

        Args:
            name: Service name

        Returns:
            ServiceMetadata for the service

        Raises:
            KeyError: If service not found
        """
        if name not in self.services:
            raise KeyError(f"Service '{name}' not found in registry")
        return self.services[name]

    def get_start_order(self, service_names: list[str]) -> list[str]:
        """Get topologically sorted start order based on dependencies.

        Uses Kahn's algorithm for topological sorting to ensure services
        are started in dependency order.

        Args:
            service_names: List of service names to order

        Returns:
            List of service names in start order

        Raises:
            KeyError: If any service name is not found
            ValueError: If circular dependency detected
        """
        # Validate all services exist
        for name in service_names:
            if name not in self.services:
                raise KeyError(f"Service '{name}' not found in registry")

        # Build dependency graph for requested services only
        in_degree: dict[str, int] = {name: 0 for name in service_names}
        graph: dict[str, list[str]] = {name: [] for name in service_names}

        for name in service_names:
            service = self.services[name]
            for dep in service.dependencies:
                # Only track dependencies that are in the requested set
                if dep in service_names:
                    graph[dep].append(name)
                    in_degree[name] += 1

        # Kahn's algorithm for topological sort
        queue = [name for name in service_names if in_degree[name] == 0]
        result: list[str] = []

        while queue:
            # Sort to ensure deterministic ordering when multiple services have same priority
            queue.sort()
            current = queue.pop(0)
            result.append(current)

            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Check for circular dependencies
        if len(result) != len(service_names):
            raise ValueError("Circular dependency detected in services")

        return result

    def get_service_group(self, group: Literal["live", "paper", "backtest", "all"]) -> list[str]:
        """Get service names in group.

        Args:
            group: Service group name

        Returns:
            List of service names in the group
        """
        if group == "all":
            return sorted(self.services.keys())

        group_services = SERVICE_GROUPS.get(group, [])
        # Filter to only include discovered services
        return [name for name in group_services if name in self.services]

    def list_services(self) -> dict[str, ServiceMetadata]:
        """List all discovered services.

        Returns:
            Dict mapping service name to metadata
        """
        return dict(self.services)
