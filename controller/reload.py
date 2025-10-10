"""Config hot-reload manager for services."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import platform
import time
from pathlib import Path
from typing import TYPE_CHECKING

from core.config import load_config

if TYPE_CHECKING:
    from core.bus import BusProto

logger = logging.getLogger(__name__)

# Config files to watch
CONFIG_FILES = ["config/base.yaml", "config/secrets.enc.yaml"]

# Reload topic for Redis pub/sub
RELOAD_TOPIC = "controller.reload"


class ConfigReloader:
    """Manager for config hot-reload without service restart.

    Watches config files for changes and sends reload signals to services
    via Redis pub/sub. Supports inotify on Linux with polling fallback.

    Attributes:
        bus: Message bus for reload signals
        config_root: Root directory for config files
        poll_interval: Polling interval in seconds (fallback mode)
        journal_dir: Directory for journaling config changes
    """

    def __init__(
        self,
        bus: BusProto,
        config_root: Path = Path("."),
        poll_interval: float = 5.0,
        journal_dir: Path = Path("var/log/njord"),
    ) -> None:
        """Initialize config reloader.

        Args:
            bus: Message bus for reload signals
            config_root: Root directory for config files
            poll_interval: Polling interval in seconds (default 5.0)
            journal_dir: Directory for journaling config changes
        """
        self.bus = bus
        self.config_root = config_root
        self.poll_interval = poll_interval
        self.journal_dir = journal_dir
        self.journal_dir.mkdir(parents=True, exist_ok=True)

        self._last_hash: str | None = None
        self._watching = False
        self._use_inotify = self._check_inotify_available()

    def _check_inotify_available(self) -> bool:
        """Check if inotify is available (Linux only).

        Returns:
            True if inotify is available, False otherwise
        """
        if platform.system() != "Linux":
            return False

        import importlib.util

        try:
            spec = importlib.util.find_spec("inotify.adapters")
            return spec is not None
        except (ImportError, ModuleNotFoundError):
            return False

    def get_config_files(self) -> list[Path]:
        """Get list of config files to watch.

        Returns:
            List of absolute paths to config files
        """
        files = []
        for file_path in CONFIG_FILES:
            full_path = (self.config_root / file_path).resolve()
            if full_path.exists():
                files.append(full_path)
        return files

    def compute_config_hash(self, config_files: list[Path] | None = None) -> str:
        """Compute SHA256 hash of config files.

        Args:
            config_files: List of config files (default: auto-discover)

        Returns:
            Hex-encoded SHA256 hash
        """
        if config_files is None:
            config_files = self.get_config_files()

        hasher = hashlib.sha256()

        # Sort files for deterministic hash
        for file_path in sorted(config_files):
            if file_path.exists():
                hasher.update(file_path.read_bytes())

        return hasher.hexdigest()

    def validate_config(self, config_path: Path | None = None) -> tuple[bool, str | None]:
        """Validate config file before reload.

        Args:
            config_path: Path to config directory (default: self.config_root)

        Returns:
            (valid, error_message)
        """
        if config_path is None:
            config_path = self.config_root

        try:
            load_config(config_path)
            return True, None
        except Exception as e:
            return False, str(e)

    async def reload_service_config(self, service_name: str) -> bool:
        """Trigger config reload for service.

        Sends reload signal via Redis pub/sub to specified service.

        Args:
            service_name: Service to reload

        Returns:
            True if reload signal sent successfully
        """
        try:
            await self.bus.publish_json(
                RELOAD_TOPIC,
                {
                    "service": service_name,
                    "timestamp_ns": time.time_ns(),
                },
            )
            logger.info(f"reload_signal_sent service={service_name}")
            return True
        except Exception as e:
            logger.error(f"reload_signal_failed service={service_name} error={e}")
            return False

    async def reload_all_services(self) -> bool:
        """Trigger config reload for all services.

        Sends broadcast reload signal via Redis pub/sub.

        Returns:
            True if reload signal sent successfully
        """
        try:
            await self.bus.publish_json(
                RELOAD_TOPIC,
                {
                    "service": "*",  # Broadcast to all
                    "timestamp_ns": time.time_ns(),
                },
            )
            logger.info("reload_signal_sent service=*")
            return True
        except Exception as e:
            logger.error(f"reload_signal_failed service=* error={e}")
            return False

    def _journal_config_change(self, old_hash: str | None, new_hash: str) -> None:
        """Journal config change with timestamp.

        Args:
            old_hash: Previous config hash
            new_hash: New config hash
        """
        journal_file = self.journal_dir / "config_changes.log"
        timestamp = time.time_ns()

        with journal_file.open("a") as f:
            f.write(f"{timestamp}\t{old_hash or 'initial'}\t{new_hash}\tconfig_changed\n")

    async def _watch_inotify(self) -> None:
        """Watch config files using inotify (Linux only)."""
        import inotify.adapters

        config_dir = self.config_root / "config"
        if not config_dir.exists():
            logger.warning(f"config_dir_not_found path={config_dir}")
            return

        i = inotify.adapters.Inotify()
        i.add_watch(str(config_dir.resolve()))

        logger.info(f"config_watch_started method=inotify path={config_dir}")

        try:
            for event in i.event_gen(yield_nones=False):
                if not self._watching:
                    break

                (_, type_names, _path, filename) = event

                # Check if this is a config file we care about
                if filename not in ["base.yaml", "secrets.enc.yaml"]:
                    continue

                # Only react to modify/close_write events
                if "IN_MODIFY" not in type_names and "IN_CLOSE_WRITE" not in type_names:
                    continue

                # Small delay to ensure write is complete
                await asyncio.sleep(0.1)

                # Check if config hash changed
                new_hash = self.compute_config_hash()
                if new_hash != self._last_hash:
                    logger.info(f"config_changed file={filename} hash={new_hash[:8]}")

                    # Validate new config
                    valid, error = self.validate_config()
                    if not valid:
                        logger.error(f"config_invalid error={error}")
                        continue

                    # Journal the change
                    self._journal_config_change(self._last_hash, new_hash)

                    # Send reload signal
                    await self.reload_all_services()

                    self._last_hash = new_hash
        finally:
            i.remove_watch(str(config_dir.resolve()))

    async def _watch_polling(self) -> None:
        """Watch config files using polling (cross-platform fallback)."""
        logger.info(f"config_watch_started method=polling interval={self.poll_interval}s")

        while self._watching:
            try:
                new_hash = self.compute_config_hash()

                if self._last_hash is not None and new_hash != self._last_hash:
                    logger.info(f"config_changed hash={new_hash[:8]}")

                    # Validate new config
                    valid, error = self.validate_config()
                    if not valid:
                        logger.error(f"config_invalid error={error}")
                        await asyncio.sleep(self.poll_interval)
                        continue

                    # Journal the change
                    self._journal_config_change(self._last_hash, new_hash)

                    # Send reload signal
                    await self.reload_all_services()

                self._last_hash = new_hash

            except Exception as e:
                logger.error(f"config_watch_error error={e}")

            await asyncio.sleep(self.poll_interval)

    async def watch_config(self) -> None:
        """Watch config files for changes.

        Uses inotify on Linux, polling fallback on other platforms.
        Runs until stopped via stop_watching().
        """
        self._watching = True

        # Initialize hash
        self._last_hash = self.compute_config_hash()
        logger.info(f"initial_config_hash hash={self._last_hash[:8]}")

        # Choose watch method
        if self._use_inotify:
            await self._watch_inotify()
        else:
            await self._watch_polling()

    def stop_watching(self) -> None:
        """Stop watching config files."""
        self._watching = False
        logger.info("config_watch_stopped")
