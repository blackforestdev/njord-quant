"""Process manager for controlling service lifecycles."""

from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
import sys
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING

from controller.contracts import ServiceStatus
from core import kill_switch

if TYPE_CHECKING:
    from controller.registry import ServiceRegistry

# Live services that require kill-switch and env var checks
LIVE_SERVICES = {"broker_binanceus"}


class ProcessManager:
    """Manager for service process lifecycles.

    Handles starting, stopping, and monitoring service processes with
    safety checks for live trading services.

    Attributes:
        registry: Service registry for service metadata
        log_dir: Directory for service log files
        processes: Dict mapping service name to Process object
    """

    def __init__(
        self,
        registry: ServiceRegistry,
        log_dir: Path = Path("var/log/njord"),
    ) -> None:
        """Initialize process manager.

        Args:
            registry: Service registry
            log_dir: Directory for log files
        """
        self.registry = registry
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.processes: dict[str, subprocess.Popen[bytes]] = {}
        self._start_times: dict[str, float] = {}

    async def start_service(
        self,
        service_name: str,
        config_root: Path = Path("."),
    ) -> ServiceStatus:
        """Start a service process.

        Performs safety checks before starting live services:
        - Checks kill-switch state (file-based)
        - Validates NJORD_ENABLE_LIVE=1 env var for live broker

        Args:
            service_name: Service to start
            config_root: Root directory for config files

        Returns:
            ServiceStatus with PID and status

        Raises:
            KeyError: If service not found in registry
            RuntimeError: If service is already running
            PermissionError: If kill-switch is tripped for live service
            PermissionError: If NJORD_ENABLE_LIVE not set for live broker
        """
        # Validate service exists
        metadata = self.registry.get_service(service_name)

        # Check if already running
        if service_name in self.processes:
            proc = self.processes[service_name]
            if proc.poll() is None:  # Still running
                raise RuntimeError(f"Service '{service_name}' is already running")

        # Safety check for live services
        if service_name in LIVE_SERVICES:
            await self._check_live_service_safety(service_name, config_root)

        # Prepare environment
        env = os.environ.copy()
        env["PYTHONPATH"] = str(config_root.resolve())

        # Prepare log files
        stdout_log = self.log_dir / f"{service_name}.stdout.log"
        stderr_log = self.log_dir / f"{service_name}.stderr.log"

        stdout_file = stdout_log.open("a")
        stderr_file = stderr_log.open("a")

        # Start process
        try:
            process = subprocess.Popen(
                [sys.executable, "-m", metadata.entry_point],
                stdout=stdout_file,
                stderr=stderr_file,
                cwd=config_root,
                env=env,
                start_new_session=True,  # Detach from parent process group
            )

            self.processes[service_name] = process
            self._start_times[service_name] = time.time()

            # Give process a moment to start
            await asyncio.sleep(0.1)

            # Check if process started successfully
            if process.poll() is not None:
                # Process already exited
                stdout_file.close()
                stderr_file.close()
                return ServiceStatus(
                    service_name=service_name,
                    status="error",
                    pid=None,
                    uptime_seconds=0,
                    last_error="Process failed to start",
                    timestamp_ns=time.time_ns(),
                )

            return ServiceStatus(
                service_name=service_name,
                status="running",
                pid=process.pid,
                uptime_seconds=0,
                last_error=None,
                timestamp_ns=time.time_ns(),
            )

        except Exception as e:
            stdout_file.close()
            stderr_file.close()
            return ServiceStatus(
                service_name=service_name,
                status="error",
                pid=None,
                uptime_seconds=0,
                last_error=str(e),
                timestamp_ns=time.time_ns(),
            )

    async def stop_service(
        self,
        service_name: str,
        timeout_seconds: int = 10,
    ) -> ServiceStatus:
        """Stop a service gracefully.

        Sends SIGTERM, waits for timeout, then sends SIGKILL if needed.

        Args:
            service_name: Service to stop
            timeout_seconds: Grace period before SIGKILL

        Returns:
            ServiceStatus after stopping

        Raises:
            KeyError: If service not found in registry
            RuntimeError: If service is not running
        """
        # Validate service exists
        _ = self.registry.get_service(service_name)

        if service_name not in self.processes:
            raise RuntimeError(f"Service '{service_name}' is not running")

        process = self.processes[service_name]

        # Check if already stopped
        if process.poll() is not None:
            del self.processes[service_name]
            del self._start_times[service_name]
            return ServiceStatus(
                service_name=service_name,
                status="stopped",
                pid=None,
                uptime_seconds=0,
                last_error=None,
                timestamp_ns=time.time_ns(),
            )

        # Send SIGTERM
        with contextlib.suppress(ProcessLookupError):
            process.terminate()

        # Wait for graceful shutdown
        try:
            process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            # Force kill
            try:
                process.kill()
                process.wait(timeout=5)
            except Exception:
                pass

        # Clean up
        del self.processes[service_name]
        del self._start_times[service_name]

        return ServiceStatus(
            service_name=service_name,
            status="stopped",
            pid=None,
            uptime_seconds=0,
            last_error=None,
            timestamp_ns=time.time_ns(),
        )

    async def restart_service(
        self,
        service_name: str,
        config_root: Path = Path("."),
    ) -> ServiceStatus:
        """Restart a service (stop + start).

        Args:
            service_name: Service to restart
            config_root: Root directory for config files

        Returns:
            ServiceStatus after restart

        Raises:
            KeyError: If service not found in registry
        """
        # Stop if running
        if service_name in self.processes:
            await self.stop_service(service_name)

        # Start service
        return await self.start_service(service_name, config_root)

    def get_status(self, service_name: str) -> ServiceStatus:
        """Get current service status.

        Args:
            service_name: Service to check

        Returns:
            ServiceStatus with PID, uptime, status

        Raises:
            KeyError: If service not found in registry
        """
        # Validate service exists
        _ = self.registry.get_service(service_name)

        if service_name not in self.processes:
            return ServiceStatus(
                service_name=service_name,
                status="stopped",
                pid=None,
                uptime_seconds=0,
                last_error=None,
                timestamp_ns=time.time_ns(),
            )

        process = self.processes[service_name]
        start_time = self._start_times.get(service_name, time.time())

        # Check if process is still running
        if process.poll() is not None:
            # Process exited
            del self.processes[service_name]
            del self._start_times[service_name]
            return ServiceStatus(
                service_name=service_name,
                status="error",
                pid=None,
                uptime_seconds=0,
                last_error="Process exited unexpectedly",
                timestamp_ns=time.time_ns(),
            )

        uptime = int(time.time() - start_time)

        return ServiceStatus(
            service_name=service_name,
            status="running",
            pid=process.pid,
            uptime_seconds=uptime,
            last_error=None,
            timestamp_ns=time.time_ns(),
        )

    async def monitor_health(
        self,
        service_name: str,
        interval_seconds: float = 5.0,
    ) -> AsyncIterator[ServiceStatus]:
        """Monitor service health continuously.

        Args:
            service_name: Service to monitor
            interval_seconds: Interval between health checks

        Yields:
            ServiceStatus updates

        Raises:
            KeyError: If service not found in registry
        """
        # Validate service exists
        _ = self.registry.get_service(service_name)

        while True:
            status = self.get_status(service_name)
            yield status

            # Stop monitoring if service is stopped or errored
            if status.status in ("stopped", "error"):
                break

            await asyncio.sleep(interval_seconds)

    async def _check_live_service_safety(
        self,
        service_name: str,
        config_root: Path,
    ) -> None:
        """Check safety requirements for live services.

        Args:
            service_name: Service name
            config_root: Config root directory

        Raises:
            PermissionError: If safety checks fail
        """
        # Load config to get kill-switch file path
        from core.config import load_config

        config = load_config(config_root / "config")
        kill_switch_file = config.risk.kill_switch_file

        # Check kill-switch (file-based)
        if kill_switch.file_tripped(kill_switch_file):
            raise PermissionError(
                f"Cannot start live service '{service_name}': kill-switch is tripped "
                f"(file: {kill_switch_file})"
            )

        # Check NJORD_ENABLE_LIVE env var
        if os.getenv("NJORD_ENABLE_LIVE") != "1":
            raise PermissionError(
                f"Cannot start live service '{service_name}': "
                "NJORD_ENABLE_LIVE environment variable must be set to '1'"
            )
