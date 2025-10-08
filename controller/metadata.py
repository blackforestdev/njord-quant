"""Service metadata definitions for controller registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ServiceGroup = Literal["live", "paper", "backtest", "all"]


@dataclass(frozen=True)
class ServiceMetadata:
    """Metadata for a managed service.

    Attributes:
        name: Service identifier (e.g., "risk_engine")
        entry_point: Python module path (e.g., "apps.risk_engine")
        directory: Absolute path to service directory
        dependencies: List of service names this service depends on
        groups: Service groups this service belongs to

    Raises:
        ValueError: If name is empty or directory doesn't exist
    """

    name: str
    entry_point: str
    directory: Path
    dependencies: list[str]
    groups: list[ServiceGroup]

    def __post_init__(self) -> None:
        """Validate ServiceMetadata configuration."""
        if not self.name:
            raise ValueError("name must not be empty")
        if not self.directory.exists():
            raise ValueError(f"directory {self.directory} does not exist")
        if not self.directory.is_dir():
            raise ValueError(f"directory {self.directory} is not a directory")
