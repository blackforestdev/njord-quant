"""Tests for controller contracts."""

from __future__ import annotations

import time

import pytest

from controller.contracts import ControlCommand, ServiceStatus, SessionSnapshot


class TestServiceStatus:
    """Tests for ServiceStatus contract."""

    def test_creates_valid_service_status_running(self) -> None:
        """Test creating valid ServiceStatus for running service."""
        ts = int(time.time() * 1e9)
        status = ServiceStatus(
            service_name="risk_engine",
            status="running",
            pid=12345,
            uptime_seconds=300,
            last_error=None,
            timestamp_ns=ts,
        )

        assert status.service_name == "risk_engine"
        assert status.status == "running"
        assert status.pid == 12345
        assert status.uptime_seconds == 300
        assert status.last_error is None
        assert status.timestamp_ns == ts

    def test_creates_valid_service_status_stopped(self) -> None:
        """Test creating valid ServiceStatus for stopped service."""
        ts = int(time.time() * 1e9)
        status = ServiceStatus(
            service_name="paper_trader",
            status="stopped",
            pid=None,
            uptime_seconds=0,
            last_error=None,
            timestamp_ns=ts,
        )

        assert status.service_name == "paper_trader"
        assert status.status == "stopped"
        assert status.pid is None
        assert status.uptime_seconds == 0

    def test_creates_valid_service_status_error(self) -> None:
        """Test creating valid ServiceStatus with error."""
        ts = int(time.time() * 1e9)
        status = ServiceStatus(
            service_name="broker",
            status="error",
            pid=None,
            uptime_seconds=0,
            last_error="Connection refused",
            timestamp_ns=ts,
        )

        assert status.service_name == "broker"
        assert status.status == "error"
        assert status.last_error == "Connection refused"

    def test_supports_all_status_types(self) -> None:
        """Test ServiceStatus supports all status types."""
        ts = int(time.time() * 1e9)
        for status_type in ["running", "stopped", "starting", "stopping", "error"]:
            status = ServiceStatus(
                service_name="test_service",
                status=status_type,  # type: ignore[arg-type]
                pid=None,
                uptime_seconds=0,
                last_error=None,
                timestamp_ns=ts,
            )
            assert status.status == status_type

    def test_rejects_empty_service_name(self) -> None:
        """Test ServiceStatus rejects empty service_name."""
        with pytest.raises(ValueError, match="service_name must not be empty"):
            ServiceStatus(
                service_name="",
                status="running",
                pid=12345,
                uptime_seconds=0,
                last_error=None,
                timestamp_ns=0,
            )

    def test_rejects_negative_uptime(self) -> None:
        """Test ServiceStatus rejects negative uptime_seconds."""
        with pytest.raises(ValueError, match="uptime_seconds must be >= 0"):
            ServiceStatus(
                service_name="test",
                status="running",
                pid=12345,
                uptime_seconds=-1,
                last_error=None,
                timestamp_ns=0,
            )

    def test_rejects_negative_timestamp(self) -> None:
        """Test ServiceStatus rejects negative timestamp_ns."""
        with pytest.raises(ValueError, match="timestamp_ns must be >= 0"):
            ServiceStatus(
                service_name="test",
                status="running",
                pid=12345,
                uptime_seconds=0,
                last_error=None,
                timestamp_ns=-1,
            )

    def test_allows_zero_uptime(self) -> None:
        """Test ServiceStatus allows zero uptime_seconds."""
        status = ServiceStatus(
            service_name="test",
            status="starting",
            pid=None,
            uptime_seconds=0,
            last_error=None,
            timestamp_ns=0,
        )
        assert status.uptime_seconds == 0

    def test_serializes_to_dict(self) -> None:
        """Test ServiceStatus serialization to dictionary."""
        ts = int(time.time() * 1e9)
        status = ServiceStatus(
            service_name="risk_engine",
            status="running",
            pid=12345,
            uptime_seconds=300,
            last_error=None,
            timestamp_ns=ts,
        )

        data = status.to_dict()

        assert data == {
            "service_name": "risk_engine",
            "status": "running",
            "pid": 12345,
            "uptime_seconds": 300,
            "last_error": None,
            "timestamp_ns": ts,
        }

    def test_deserializes_from_dict(self) -> None:
        """Test ServiceStatus deserialization from dictionary."""
        ts = int(time.time() * 1e9)
        data = {
            "service_name": "paper_trader",
            "status": "stopped",
            "pid": None,
            "uptime_seconds": 0,
            "last_error": None,
            "timestamp_ns": ts,
        }

        status = ServiceStatus.from_dict(data)

        assert status.service_name == "paper_trader"
        assert status.status == "stopped"
        assert status.pid is None
        assert status.uptime_seconds == 0
        assert status.last_error is None
        assert status.timestamp_ns == ts

    def test_roundtrip_serialization(self) -> None:
        """Test ServiceStatus roundtrip serialization."""
        ts = int(time.time() * 1e9)
        original = ServiceStatus(
            service_name="broker",
            status="error",
            pid=None,
            uptime_seconds=0,
            last_error="Connection timeout",
            timestamp_ns=ts,
        )

        data = original.to_dict()
        restored = ServiceStatus.from_dict(data)

        assert restored == original

    def test_immutable(self) -> None:
        """Test ServiceStatus is immutable."""
        status = ServiceStatus(
            service_name="test",
            status="running",
            pid=12345,
            uptime_seconds=0,
            last_error=None,
            timestamp_ns=0,
        )

        with pytest.raises(AttributeError):
            status.pid = 67890  # type: ignore[misc]


class TestSessionSnapshot:
    """Tests for SessionSnapshot contract."""

    def test_creates_valid_session_snapshot_active(self) -> None:
        """Test creating valid SessionSnapshot for active session."""
        ts = int(time.time() * 1e9)
        snapshot = SessionSnapshot(
            session_id="sess_abc123",
            start_ts_ns=ts,
            end_ts_ns=None,
            services=["risk_engine", "paper_trader", "broker"],
            config_hash="a" * 64,
            status="active",
        )

        assert snapshot.session_id == "sess_abc123"
        assert snapshot.start_ts_ns == ts
        assert snapshot.end_ts_ns is None
        assert snapshot.services == ["risk_engine", "paper_trader", "broker"]
        assert snapshot.config_hash == "a" * 64
        assert snapshot.status == "active"

    def test_creates_valid_session_snapshot_stopped(self) -> None:
        """Test creating valid SessionSnapshot for stopped session."""
        start_ts = int(time.time() * 1e9)
        end_ts = start_ts + 3600 * int(1e9)  # 1 hour later
        snapshot = SessionSnapshot(
            session_id="sess_xyz789",
            start_ts_ns=start_ts,
            end_ts_ns=end_ts,
            services=["risk_engine"],
            config_hash="b" * 64,
            status="stopped",
        )

        assert snapshot.session_id == "sess_xyz789"
        assert snapshot.start_ts_ns == start_ts
        assert snapshot.end_ts_ns == end_ts
        assert snapshot.status == "stopped"

    def test_supports_all_session_status_types(self) -> None:
        """Test SessionSnapshot supports all status types."""
        ts = int(time.time() * 1e9)
        for status_type in ["active", "stopped", "error"]:
            snapshot = SessionSnapshot(
                session_id="test_session",
                start_ts_ns=ts,
                end_ts_ns=None,
                services=["test"],
                config_hash="c" * 64,
                status=status_type,  # type: ignore[arg-type]
            )
            assert snapshot.status == status_type

    def test_allows_empty_services_list(self) -> None:
        """Test SessionSnapshot allows empty services list."""
        snapshot = SessionSnapshot(
            session_id="test",
            start_ts_ns=0,
            end_ts_ns=None,
            services=[],
            config_hash="d" * 64,
            status="active",
        )
        assert snapshot.services == []

    def test_rejects_empty_session_id(self) -> None:
        """Test SessionSnapshot rejects empty session_id."""
        with pytest.raises(ValueError, match="session_id must not be empty"):
            SessionSnapshot(
                session_id="",
                start_ts_ns=0,
                end_ts_ns=None,
                services=[],
                config_hash="e" * 64,
                status="active",
            )

    def test_rejects_negative_start_timestamp(self) -> None:
        """Test SessionSnapshot rejects negative start_ts_ns."""
        with pytest.raises(ValueError, match="start_ts_ns must be >= 0"):
            SessionSnapshot(
                session_id="test",
                start_ts_ns=-1,
                end_ts_ns=None,
                services=[],
                config_hash="f" * 64,
                status="active",
            )

    def test_rejects_negative_end_timestamp(self) -> None:
        """Test SessionSnapshot rejects negative end_ts_ns."""
        with pytest.raises(ValueError, match="end_ts_ns must be >= 0"):
            SessionSnapshot(
                session_id="test",
                start_ts_ns=0,
                end_ts_ns=-1,
                services=[],
                config_hash="g" * 64,
                status="stopped",
            )

    def test_rejects_end_before_start(self) -> None:
        """Test SessionSnapshot rejects end_ts_ns before start_ts_ns."""
        with pytest.raises(ValueError, match=r"end_ts_ns .* must be >= start_ts_ns"):
            SessionSnapshot(
                session_id="test",
                start_ts_ns=1000,
                end_ts_ns=999,
                services=[],
                config_hash="h" * 64,
                status="stopped",
            )

    def test_allows_end_equal_to_start(self) -> None:
        """Test SessionSnapshot allows end_ts_ns equal to start_ts_ns."""
        snapshot = SessionSnapshot(
            session_id="test",
            start_ts_ns=1000,
            end_ts_ns=1000,
            services=[],
            config_hash="i" * 64,
            status="stopped",
        )
        assert snapshot.end_ts_ns == snapshot.start_ts_ns

    def test_rejects_empty_config_hash(self) -> None:
        """Test SessionSnapshot rejects empty config_hash."""
        with pytest.raises(ValueError, match="config_hash must not be empty"):
            SessionSnapshot(
                session_id="test",
                start_ts_ns=0,
                end_ts_ns=None,
                services=[],
                config_hash="",
                status="active",
            )

    def test_serializes_to_dict(self) -> None:
        """Test SessionSnapshot serialization to dictionary."""
        ts = int(time.time() * 1e9)
        snapshot = SessionSnapshot(
            session_id="sess_123",
            start_ts_ns=ts,
            end_ts_ns=None,
            services=["risk_engine", "paper_trader"],
            config_hash="j" * 64,
            status="active",
        )

        data = snapshot.to_dict()

        assert data == {
            "session_id": "sess_123",
            "start_ts_ns": ts,
            "end_ts_ns": None,
            "services": ["risk_engine", "paper_trader"],
            "config_hash": "j" * 64,
            "status": "active",
        }

    def test_deserializes_from_dict(self) -> None:
        """Test SessionSnapshot deserialization from dictionary."""
        ts = int(time.time() * 1e9)
        data = {
            "session_id": "sess_456",
            "start_ts_ns": ts,
            "end_ts_ns": None,
            "services": ["broker"],
            "config_hash": "k" * 64,
            "status": "active",
        }

        snapshot = SessionSnapshot.from_dict(data)

        assert snapshot.session_id == "sess_456"
        assert snapshot.start_ts_ns == ts
        assert snapshot.end_ts_ns is None
        assert snapshot.services == ["broker"]
        assert snapshot.config_hash == "k" * 64
        assert snapshot.status == "active"

    def test_roundtrip_serialization(self) -> None:
        """Test SessionSnapshot roundtrip serialization."""
        start_ts = int(time.time() * 1e9)
        end_ts = start_ts + 1000
        original = SessionSnapshot(
            session_id="sess_789",
            start_ts_ns=start_ts,
            end_ts_ns=end_ts,
            services=["risk_engine", "paper_trader", "broker"],
            config_hash="l" * 64,
            status="stopped",
        )

        data = original.to_dict()
        restored = SessionSnapshot.from_dict(data)

        assert restored == original

    def test_immutable(self) -> None:
        """Test SessionSnapshot is immutable."""
        snapshot = SessionSnapshot(
            session_id="test",
            start_ts_ns=0,
            end_ts_ns=None,
            services=[],
            config_hash="m" * 64,
            status="active",
        )

        with pytest.raises(AttributeError):
            snapshot.status = "stopped"  # type: ignore[misc]


class TestControlCommand:
    """Tests for ControlCommand contract."""

    def test_creates_valid_control_command_start(self) -> None:
        """Test creating valid ControlCommand for start operation."""
        ts = int(time.time() * 1e9)
        cmd = ControlCommand(
            command="start",
            service_names=["risk_engine", "paper_trader"],
            session_id="sess_abc",
            timestamp_ns=ts,
        )

        assert cmd.command == "start"
        assert cmd.service_names == ["risk_engine", "paper_trader"]
        assert cmd.session_id == "sess_abc"
        assert cmd.timestamp_ns == ts

    def test_creates_valid_control_command_stop_all(self) -> None:
        """Test creating valid ControlCommand for stop all services."""
        ts = int(time.time() * 1e9)
        cmd = ControlCommand(
            command="stop",
            service_names=[],
            session_id="sess_xyz",
            timestamp_ns=ts,
        )

        assert cmd.command == "stop"
        assert cmd.service_names == []
        assert cmd.session_id == "sess_xyz"

    def test_supports_all_command_types(self) -> None:
        """Test ControlCommand supports all command types."""
        ts = int(time.time() * 1e9)
        for command_type in ["start", "stop", "restart", "reload", "status"]:
            cmd = ControlCommand(
                command=command_type,  # type: ignore[arg-type]
                service_names=[],
                session_id="test_session",
                timestamp_ns=ts,
            )
            assert cmd.command == command_type

    def test_allows_empty_service_names_for_all_services(self) -> None:
        """Test ControlCommand allows empty service_names list."""
        cmd = ControlCommand(
            command="status",
            service_names=[],
            session_id="test",
            timestamp_ns=0,
        )
        assert cmd.service_names == []

    def test_rejects_empty_session_id(self) -> None:
        """Test ControlCommand rejects empty session_id."""
        with pytest.raises(ValueError, match="session_id must not be empty"):
            ControlCommand(
                command="start",
                service_names=[],
                session_id="",
                timestamp_ns=0,
            )

    def test_rejects_negative_timestamp(self) -> None:
        """Test ControlCommand rejects negative timestamp_ns."""
        with pytest.raises(ValueError, match="timestamp_ns must be >= 0"):
            ControlCommand(
                command="start",
                service_names=[],
                session_id="test",
                timestamp_ns=-1,
            )

    def test_serializes_to_dict(self) -> None:
        """Test ControlCommand serialization to dictionary."""
        ts = int(time.time() * 1e9)
        cmd = ControlCommand(
            command="restart",
            service_names=["broker"],
            session_id="sess_123",
            timestamp_ns=ts,
        )

        data = cmd.to_dict()

        assert data == {
            "command": "restart",
            "service_names": ["broker"],
            "session_id": "sess_123",
            "timestamp_ns": ts,
        }

    def test_deserializes_from_dict(self) -> None:
        """Test ControlCommand deserialization from dictionary."""
        ts = int(time.time() * 1e9)
        data = {
            "command": "reload",
            "service_names": ["risk_engine"],
            "session_id": "sess_456",
            "timestamp_ns": ts,
        }

        cmd = ControlCommand.from_dict(data)

        assert cmd.command == "reload"
        assert cmd.service_names == ["risk_engine"]
        assert cmd.session_id == "sess_456"
        assert cmd.timestamp_ns == ts

    def test_roundtrip_serialization(self) -> None:
        """Test ControlCommand roundtrip serialization."""
        ts = int(time.time() * 1e9)
        original = ControlCommand(
            command="stop",
            service_names=["risk_engine", "paper_trader", "broker"],
            session_id="sess_789",
            timestamp_ns=ts,
        )

        data = original.to_dict()
        restored = ControlCommand.from_dict(data)

        assert restored == original

    def test_immutable(self) -> None:
        """Test ControlCommand is immutable."""
        cmd = ControlCommand(
            command="start",
            service_names=[],
            session_id="test",
            timestamp_ns=0,
        )

        with pytest.raises(AttributeError):
            cmd.command = "stop"  # type: ignore[misc]
