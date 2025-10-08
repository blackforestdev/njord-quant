"""Controller contracts for service management and session tracking.

This module defines contracts for the njord-ctl CLI and controller service,
including service status tracking, session management, and control commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ServiceStatusType = Literal["running", "stopped", "starting", "stopping", "error"]
SessionStatusType = Literal["active", "stopped", "error"]
ControlCommandType = Literal["start", "stop", "restart", "reload", "status"]


@dataclass(frozen=True)
class ServiceStatus:
    """Status of a single service.

    Represents the current state of a managed service including process
    information, runtime duration, and error state.

    Attributes:
        service_name: Service identifier (e.g., "risk_engine", "paper_trader")
        status: Current service state
        pid: Process ID if running, None otherwise
        uptime_seconds: Seconds since service started (0 if stopped)
        last_error: Last error message if status is "error", None otherwise
        timestamp_ns: Status snapshot timestamp (nanoseconds since epoch)

    Raises:
        ValueError: If service_name is empty, uptime is negative, or timestamp is negative
    """

    service_name: str
    status: ServiceStatusType
    pid: int | None
    uptime_seconds: int
    last_error: str | None
    timestamp_ns: int

    def __post_init__(self) -> None:
        """Validate ServiceStatus configuration."""
        if not self.service_name:
            raise ValueError("service_name must not be empty")
        if self.uptime_seconds < 0:
            raise ValueError(f"uptime_seconds must be >= 0, got {self.uptime_seconds}")
        if self.timestamp_ns < 0:
            raise ValueError(f"timestamp_ns must be >= 0, got {self.timestamp_ns}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of ServiceStatus
        """
        return {
            "service_name": self.service_name,
            "status": self.status,
            "pid": self.pid,
            "uptime_seconds": self.uptime_seconds,
            "last_error": self.last_error,
            "timestamp_ns": self.timestamp_ns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceStatus:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with service status data

        Returns:
            ServiceStatus instance
        """
        return cls(
            service_name=data["service_name"],
            status=data["status"],
            pid=data.get("pid"),
            uptime_seconds=data["uptime_seconds"],
            last_error=data.get("last_error"),
            timestamp_ns=data["timestamp_ns"],
        )


@dataclass(frozen=True)
class SessionSnapshot:
    """Trading session metadata.

    Represents a trading session with tracked services, configuration state,
    and session lifecycle information.

    Attributes:
        session_id: Unique session identifier (e.g., UUID)
        start_ts_ns: Session start timestamp (nanoseconds since epoch)
        end_ts_ns: Session end timestamp if stopped, None if active
        services: List of service names participating in session
        config_hash: SHA256 hash of configuration files for reload detection
        status: Current session state

    Raises:
        ValueError: If session_id is empty, start_ts_ns is negative,
                    end_ts_ns is before start_ts_ns, or config_hash is empty
    """

    session_id: str
    start_ts_ns: int
    end_ts_ns: int | None
    services: list[str]
    config_hash: str
    status: SessionStatusType

    def __post_init__(self) -> None:
        """Validate SessionSnapshot configuration."""
        if not self.session_id:
            raise ValueError("session_id must not be empty")
        if self.start_ts_ns < 0:
            raise ValueError(f"start_ts_ns must be >= 0, got {self.start_ts_ns}")
        if self.end_ts_ns is not None:
            if self.end_ts_ns < 0:
                raise ValueError(f"end_ts_ns must be >= 0, got {self.end_ts_ns}")
            if self.end_ts_ns < self.start_ts_ns:
                raise ValueError(
                    f"end_ts_ns ({self.end_ts_ns}) must be >= start_ts_ns ({self.start_ts_ns})"
                )
        if not self.config_hash:
            raise ValueError("config_hash must not be empty")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of SessionSnapshot
        """
        return {
            "session_id": self.session_id,
            "start_ts_ns": self.start_ts_ns,
            "end_ts_ns": self.end_ts_ns,
            "services": list(self.services),
            "config_hash": self.config_hash,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionSnapshot:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with session snapshot data

        Returns:
            SessionSnapshot instance
        """
        return cls(
            session_id=data["session_id"],
            start_ts_ns=data["start_ts_ns"],
            end_ts_ns=data.get("end_ts_ns"),
            services=list(data["services"]),
            config_hash=data["config_hash"],
            status=data["status"],
        )


@dataclass(frozen=True)
class ControlCommand:
    """Command to control services.

    Represents a control operation to be executed on one or more services
    within a session context.

    Attributes:
        command: Control operation to perform
        service_names: List of service names to operate on (empty list = all services)
        session_id: Session identifier for command tracking
        timestamp_ns: Command creation timestamp (nanoseconds since epoch)

    Raises:
        ValueError: If session_id is empty or timestamp_ns is negative
    """

    command: ControlCommandType
    service_names: list[str]
    session_id: str
    timestamp_ns: int

    def __post_init__(self) -> None:
        """Validate ControlCommand configuration."""
        if not self.session_id:
            raise ValueError("session_id must not be empty")
        if self.timestamp_ns < 0:
            raise ValueError(f"timestamp_ns must be >= 0, got {self.timestamp_ns}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary.

        Returns:
            Dictionary representation of ControlCommand
        """
        return {
            "command": self.command,
            "service_names": list(self.service_names),
            "session_id": self.session_id,
            "timestamp_ns": self.timestamp_ns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ControlCommand:
        """Deserialize from dictionary.

        Args:
            data: Dictionary with control command data

        Returns:
            ControlCommand instance
        """
        return cls(
            command=data["command"],
            service_names=list(data["service_names"]),
            session_id=data["session_id"],
            timestamp_ns=data["timestamp_ns"],
        )
