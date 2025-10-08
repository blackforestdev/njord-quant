"""Tests for process manager."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from controller.process_manager import LIVE_SERVICES, ProcessManager
from controller.registry import ServiceRegistry


class TestProcessManager:
    """Tests for ProcessManager."""

    @pytest.fixture
    def mock_registry(self, tmp_path: Path) -> ServiceRegistry:
        """Create a mock service registry with test services."""
        apps_dir = tmp_path / "apps"
        apps_dir.mkdir()

        # Create test services
        for service_name in ["service_a", "service_b", "live_service"]:
            service_dir = apps_dir / service_name
            service_dir.mkdir()
            (service_dir / "__main__.py").touch()

        return ServiceRegistry(apps_dir=apps_dir)

    @pytest.fixture
    def process_manager(self, mock_registry: ServiceRegistry, tmp_path: Path) -> ProcessManager:
        """Create ProcessManager with mock registry."""
        log_dir = tmp_path / "logs"
        return ProcessManager(registry=mock_registry, log_dir=log_dir)

    def test_initializes_with_log_directory(self, tmp_path: Path) -> None:
        """Test ProcessManager creates log directory on init."""
        log_dir = tmp_path / "custom_logs"
        registry = ServiceRegistry(apps_dir=tmp_path / "apps")

        manager = ProcessManager(registry=registry, log_dir=log_dir)

        assert manager.log_dir == log_dir
        assert log_dir.exists()
        assert log_dir.is_dir()

    def test_initializes_with_default_log_directory(self, tmp_path: Path) -> None:
        """Test ProcessManager uses default log directory."""
        registry = ServiceRegistry(apps_dir=tmp_path / "apps")

        manager = ProcessManager(registry=registry)

        assert manager.log_dir == Path("var/log/njord")

    @pytest.mark.asyncio
    async def test_start_service_success(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test starting a service successfully."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Still running

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("builtins.open", MagicMock()),
        ):
            status = await process_manager.start_service("service_a", config_root=tmp_path)

        assert status.service_name == "service_a"
        assert status.status == "running"
        assert status.pid == 12345
        assert status.uptime_seconds == 0
        assert status.last_error is None
        assert "service_a" in process_manager.processes

    @pytest.mark.asyncio
    async def test_start_service_creates_log_files(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test starting a service creates log files."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = None

        opened_files: list[str] = []

        def track_open(self: Path, mode: str, *args: object, **kwargs: object) -> MagicMock:
            opened_files.append(str(self))
            return MagicMock()

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch.object(Path, "open", track_open),
        ):
            await process_manager.start_service("service_a", config_root=tmp_path)

        # Check stdout and stderr log files were opened
        log_dir = process_manager.log_dir
        assert str(log_dir / "service_a.stdout.log") in opened_files
        assert str(log_dir / "service_a.stderr.log") in opened_files

    @pytest.mark.asyncio
    async def test_start_service_raises_for_missing_service(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test starting nonexistent service raises KeyError."""
        with pytest.raises(KeyError, match="Service 'nonexistent' not found"):
            await process_manager.start_service("nonexistent", config_root=tmp_path)

    @pytest.mark.asyncio
    async def test_start_service_raises_for_already_running(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test starting already running service raises RuntimeError."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Still running

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("builtins.open", MagicMock()),
        ):
            await process_manager.start_service("service_a", config_root=tmp_path)

        # Try to start again
        with pytest.raises(RuntimeError, match="Service 'service_a' is already running"):
            await process_manager.start_service("service_a", config_root=tmp_path)

    @pytest.mark.asyncio
    async def test_start_service_allows_restart_if_process_exited(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test can start service again if process exited."""
        mock_process1 = MagicMock(spec=subprocess.Popen)
        mock_process1.pid = 12345
        mock_process1.poll.return_value = None  # Initially running

        with (
            patch("subprocess.Popen", return_value=mock_process1),
            patch("builtins.open", MagicMock()),
        ):
            await process_manager.start_service("service_a", config_root=tmp_path)

        # Simulate process exit
        mock_process1.poll.return_value = 1  # Exited

        # Should be able to start again with new process
        mock_process2 = MagicMock(spec=subprocess.Popen)
        mock_process2.pid = 67890
        mock_process2.poll.return_value = None  # Running

        with (
            patch("subprocess.Popen", return_value=mock_process2),
            patch("builtins.open", MagicMock()),
        ):
            status = await process_manager.start_service("service_a", config_root=tmp_path)

        assert status.status == "running"
        assert status.pid == 67890

    @pytest.mark.asyncio
    async def test_start_service_handles_process_failure(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test starting service that immediately fails."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = 1  # Already exited

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("builtins.open", MagicMock()),
        ):
            status = await process_manager.start_service("service_a", config_root=tmp_path)

        assert status.service_name == "service_a"
        assert status.status == "error"
        assert status.pid is None
        assert status.last_error == "Process failed to start"

    @pytest.mark.asyncio
    async def test_start_service_handles_exception(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test starting service that raises exception."""
        with (
            patch("subprocess.Popen", side_effect=OSError("Permission denied")),
            patch("builtins.open", MagicMock()),
        ):
            status = await process_manager.start_service("service_a", config_root=tmp_path)

        assert status.status == "error"
        assert status.last_error == "Permission denied"

    @pytest.mark.asyncio
    async def test_start_live_service_checks_kill_switch(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test starting live service checks kill-switch."""
        # Add live_service to LIVE_SERVICES for this test
        with patch("controller.process_manager.LIVE_SERVICES", {"service_a"}):
            # Mock config loading
            mock_config = MagicMock()
            mock_config.risk.kill_switch_file = "/tmp/kill_switch"

            with (
                patch("core.config.load_config", return_value=mock_config),
                patch("core.kill_switch.file_tripped", return_value=True),
                pytest.raises(PermissionError, match="kill-switch is tripped"),
            ):
                await process_manager.start_service("service_a", config_root=tmp_path)

    @pytest.mark.asyncio
    async def test_start_live_service_checks_env_var(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test starting live service checks NJORD_ENABLE_LIVE env var."""
        # Add service_a to LIVE_SERVICES for this test
        with patch("controller.process_manager.LIVE_SERVICES", {"service_a"}):
            # Mock config loading
            mock_config = MagicMock()
            mock_config.risk.kill_switch_file = "/tmp/kill_switch"

            with (
                patch("core.config.load_config", return_value=mock_config),
                patch("core.kill_switch.file_tripped", return_value=False),
                patch.dict(os.environ, {}, clear=True),  # No NJORD_ENABLE_LIVE
                pytest.raises(
                    PermissionError,
                    match=r"NJORD_ENABLE_LIVE environment variable must be set to '1'",
                ),
            ):
                await process_manager.start_service("service_a", config_root=tmp_path)

    @pytest.mark.asyncio
    async def test_start_live_service_succeeds_with_safety_checks(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test starting live service succeeds when safety checks pass."""
        # Add service_a to LIVE_SERVICES for this test
        with patch("controller.process_manager.LIVE_SERVICES", {"service_a"}):
            # Mock config loading
            mock_config = MagicMock()
            mock_config.risk.kill_switch_file = "/tmp/kill_switch"

            mock_process = MagicMock(spec=subprocess.Popen)
            mock_process.pid = 12345
            mock_process.poll.return_value = None

            with (
                patch("core.config.load_config", return_value=mock_config),
                patch("core.kill_switch.file_tripped", return_value=False),
                patch.dict(os.environ, {"NJORD_ENABLE_LIVE": "1"}),
                patch("subprocess.Popen", return_value=mock_process),
                patch("builtins.open", MagicMock()),
            ):
                status = await process_manager.start_service("service_a", config_root=tmp_path)

            assert status.status == "running"
            assert status.pid == 12345

    @pytest.mark.asyncio
    async def test_stop_service_gracefully(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test stopping a running service gracefully."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        # First call (during start check): running, second call (during stop check): still running
        mock_process.poll.side_effect = [None, None]

        # Start service
        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("builtins.open", MagicMock()),
        ):
            await process_manager.start_service("service_a", config_root=tmp_path)

        # Simulate graceful shutdown - wait() succeeds
        mock_process.wait = MagicMock()

        status = await process_manager.stop_service("service_a")

        assert status.service_name == "service_a"
        assert status.status == "stopped"
        assert status.pid is None
        mock_process.terminate.assert_called_once()
        mock_process.wait.assert_called_once()
        assert "service_a" not in process_manager.processes

    @pytest.mark.asyncio
    async def test_stop_service_raises_for_missing_service(
        self,
        process_manager: ProcessManager,
    ) -> None:
        """Test stopping nonexistent service raises KeyError."""
        with pytest.raises(KeyError, match="Service 'nonexistent' not found"):
            await process_manager.stop_service("nonexistent")

    @pytest.mark.asyncio
    async def test_stop_service_raises_for_not_running(
        self,
        process_manager: ProcessManager,
    ) -> None:
        """Test stopping not running service raises RuntimeError."""
        with pytest.raises(RuntimeError, match="Service 'service_a' is not running"):
            await process_manager.stop_service("service_a")

    @pytest.mark.asyncio
    async def test_stop_service_handles_already_stopped(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test stopping service that already exited."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = None

        # Start service
        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("builtins.open", MagicMock()),
        ):
            await process_manager.start_service("service_a", config_root=tmp_path)

        # Simulate process already exited
        mock_process.poll.return_value = 0

        status = await process_manager.stop_service("service_a")

        assert status.status == "stopped"
        # Should not call terminate if already stopped
        mock_process.terminate.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_service_forces_kill_after_timeout(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test stopping service forces kill after timeout."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = None

        # Start service
        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("builtins.open", MagicMock()),
        ):
            await process_manager.start_service("service_a", config_root=tmp_path)

        # Simulate timeout on graceful shutdown
        mock_process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 10), None]

        status = await process_manager.stop_service("service_a", timeout_seconds=1)

        assert status.status == "stopped"
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_service_handles_process_lookup_error(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test stopping service handles ProcessLookupError."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = None

        # Start service
        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("builtins.open", MagicMock()),
        ):
            await process_manager.start_service("service_a", config_root=tmp_path)

        # Simulate process already gone
        mock_process.terminate.side_effect = ProcessLookupError()
        mock_process.wait = MagicMock()

        status = await process_manager.stop_service("service_a")

        assert status.status == "stopped"

    @pytest.mark.asyncio
    async def test_restart_service(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test restarting a service."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = None

        # Start service
        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("builtins.open", MagicMock()),
        ):
            await process_manager.start_service("service_a", config_root=tmp_path)

        # Restart
        mock_process.poll.return_value = 0  # Stopped
        mock_process.wait = MagicMock()

        new_mock_process = MagicMock(spec=subprocess.Popen)
        new_mock_process.pid = 67890
        new_mock_process.poll.return_value = None

        with (
            patch("subprocess.Popen", return_value=new_mock_process),
            patch("builtins.open", MagicMock()),
        ):
            status = await process_manager.restart_service("service_a", config_root=tmp_path)

        assert status.status == "running"
        assert status.pid == 67890

    @pytest.mark.asyncio
    async def test_restart_service_when_not_running(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test restarting service that is not running."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = None

        with (
            patch("subprocess.Popen", return_value=mock_process),
            patch("builtins.open", MagicMock()),
        ):
            status = await process_manager.restart_service("service_a", config_root=tmp_path)

        assert status.status == "running"
        assert status.pid == 12345

    def test_get_status_running_service(
        self,
        process_manager: ProcessManager,
        tmp_path: Path,
    ) -> None:
        """Test getting status of running service."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = None

        # Manually add to processes (simulating started service)
        process_manager.processes["service_a"] = mock_process
        process_manager._start_times["service_a"] = time.time() - 100  # Started 100s ago

        status = process_manager.get_status("service_a")

        assert status.service_name == "service_a"
        assert status.status == "running"
        assert status.pid == 12345
        assert status.uptime_seconds >= 100
        assert status.last_error is None

    def test_get_status_stopped_service(
        self,
        process_manager: ProcessManager,
    ) -> None:
        """Test getting status of stopped service."""
        status = process_manager.get_status("service_a")

        assert status.service_name == "service_a"
        assert status.status == "stopped"
        assert status.pid is None
        assert status.uptime_seconds == 0
        assert status.last_error is None

    def test_get_status_exited_service(
        self,
        process_manager: ProcessManager,
    ) -> None:
        """Test getting status of service that exited unexpectedly."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = 1  # Exited

        # Manually add to processes
        process_manager.processes["service_a"] = mock_process
        process_manager._start_times["service_a"] = time.time()

        status = process_manager.get_status("service_a")

        assert status.status == "error"
        assert status.pid is None
        assert status.last_error == "Process exited unexpectedly"
        # Should be cleaned up
        assert "service_a" not in process_manager.processes

    def test_get_status_raises_for_missing_service(
        self,
        process_manager: ProcessManager,
    ) -> None:
        """Test get_status raises KeyError for missing service."""
        with pytest.raises(KeyError, match="Service 'nonexistent' not found"):
            process_manager.get_status("nonexistent")

    @pytest.mark.asyncio
    async def test_monitor_health_running_service(
        self,
        process_manager: ProcessManager,
    ) -> None:
        """Test monitoring health of running service."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345
        mock_process.poll.return_value = None

        process_manager.processes["service_a"] = mock_process
        process_manager._start_times["service_a"] = time.time()

        statuses = []
        async for status in process_manager.monitor_health("service_a", interval_seconds=0.05):
            statuses.append(status)
            if len(statuses) >= 3:
                break

        assert len(statuses) == 3
        assert all(s.status == "running" for s in statuses)
        assert all(s.pid == 12345 for s in statuses)

    @pytest.mark.asyncio
    async def test_monitor_health_stops_when_service_stops(
        self,
        process_manager: ProcessManager,
    ) -> None:
        """Test monitoring stops when service stops."""
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 12345

        # First call: running, second call: stopped
        mock_process.poll.side_effect = [None, 0]

        process_manager.processes["service_a"] = mock_process
        process_manager._start_times["service_a"] = time.time()

        statuses = []
        async for status in process_manager.monitor_health("service_a", interval_seconds=0.05):
            statuses.append(status)

        # Should get one "running" status, then one "error" status, then stop
        assert len(statuses) == 2
        assert statuses[0].status == "running"
        assert statuses[1].status == "error"

    @pytest.mark.asyncio
    async def test_monitor_health_raises_for_missing_service(
        self,
        process_manager: ProcessManager,
    ) -> None:
        """Test monitor_health raises KeyError for missing service."""
        with pytest.raises(KeyError, match="Service 'nonexistent' not found"):
            async for _ in process_manager.monitor_health("nonexistent"):
                pass

    def test_live_services_constant(self) -> None:
        """Test LIVE_SERVICES constant is defined correctly."""
        assert "broker_binanceus" in LIVE_SERVICES
        assert isinstance(LIVE_SERVICES, set)
