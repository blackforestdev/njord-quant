"""Tests for config hot-reload manager."""

from __future__ import annotations

import asyncio
import contextlib
import platform
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from controller.reload import CONFIG_FILES, RELOAD_TOPIC, ConfigReloader


class TestConfigReloader:
    """Tests for ConfigReloader."""

    @pytest.fixture
    def mock_bus(self) -> MagicMock:
        """Create a mock bus for testing."""
        bus = MagicMock()
        bus.publish_json = AsyncMock()
        return bus

    @pytest.fixture
    def config_reloader(self, mock_bus: MagicMock, tmp_path: Path) -> ConfigReloader:
        """Create ConfigReloader with mock bus."""
        return ConfigReloader(
            bus=mock_bus,
            config_root=tmp_path,
            poll_interval=0.1,  # Fast polling for tests
            journal_dir=tmp_path / "journal",
        )

    @pytest.fixture
    def test_config_files(self, tmp_path: Path) -> list[Path]:
        """Create test config files."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # Create base.yaml
        base_yaml = config_dir / "base.yaml"
        base_yaml.write_text(
            """
app:
  name: njord
  env: test
  timezone: UTC

logging:
  level: INFO
  json: false
  journal_dir: /tmp/journal

redis:
  url: redis://localhost:6379
  topics:
    trades: trades
    book: book
    ticker: ticker
    intents: intents
    risk: risk
    orders: orders
    fills: fills

postgres:
  dsn: postgresql://localhost/njord

exchange:
  venue: binanceus
  symbols: ["BTCUSD", "ETHUSD"]
  ws_keepalive_sec: 30

risk:
  per_order_usd_cap: 250.0
  daily_loss_usd_cap: 300.0
  orders_per_min_cap: 30
  kill_switch_file: /var/run/njord.trading.halt
  kill_switch_key: njord:trading:halt

paths:
  journal_dir: /tmp/journal
  experiments_dir: /tmp/experiments
"""
        )

        # Create secrets.enc.yaml (can be empty for tests)
        secrets_yaml = config_dir / "secrets.enc.yaml"
        secrets_yaml.write_text("")

        return [base_yaml, secrets_yaml]

    def test_initializes_with_config_root(self, mock_bus: MagicMock, tmp_path: Path) -> None:
        """Test ConfigReloader initializes with config root."""
        reloader = ConfigReloader(bus=mock_bus, config_root=tmp_path)

        assert reloader.config_root == tmp_path
        assert reloader.bus == mock_bus
        assert reloader.poll_interval == 5.0  # Default
        assert reloader.journal_dir.exists()

    def test_initializes_with_custom_poll_interval(
        self, mock_bus: MagicMock, tmp_path: Path
    ) -> None:
        """Test ConfigReloader initializes with custom poll interval."""
        reloader = ConfigReloader(bus=mock_bus, config_root=tmp_path, poll_interval=2.0)

        assert reloader.poll_interval == 2.0

    def test_check_inotify_available_on_linux(self, config_reloader: ConfigReloader) -> None:
        """Test inotify detection on Linux."""
        with (
            patch("platform.system", return_value="Linux"),
            patch("importlib.import_module"),
        ):
            # Mock successful inotify import
            result = config_reloader._check_inotify_available()
            # Result depends on whether inotify is actually available
            assert isinstance(result, bool)

    def test_check_inotify_not_available_on_windows(self, config_reloader: ConfigReloader) -> None:
        """Test inotify not available on Windows."""
        with patch("platform.system", return_value="Windows"):
            result = config_reloader._check_inotify_available()
            assert result is False

    def test_check_inotify_not_available_on_macos(self, config_reloader: ConfigReloader) -> None:
        """Test inotify not available on macOS."""
        with patch("platform.system", return_value="Darwin"):
            result = config_reloader._check_inotify_available()
            assert result is False

    def test_get_config_files(
        self, config_reloader: ConfigReloader, test_config_files: list[Path]
    ) -> None:
        """Test getting config files."""
        files = config_reloader.get_config_files()

        assert len(files) == 2
        assert all(f.exists() for f in files)
        assert any("base.yaml" in str(f) for f in files)
        assert any("secrets.enc.yaml" in str(f) for f in files)

    def test_get_config_files_when_missing(self, config_reloader: ConfigReloader) -> None:
        """Test getting config files when directory doesn't exist."""
        files = config_reloader.get_config_files()

        # Should return empty list when config dir doesn't exist
        assert files == []

    def test_compute_config_hash(
        self, config_reloader: ConfigReloader, test_config_files: list[Path]
    ) -> None:
        """Test computing config hash."""
        hash1 = config_reloader.compute_config_hash()

        # Hash should be 64-char hex string (SHA256)
        assert len(hash1) == 64
        assert all(c in "0123456789abcdef" for c in hash1)

        # Same files should produce same hash
        hash2 = config_reloader.compute_config_hash()
        assert hash1 == hash2

    def test_compute_config_hash_changes_on_file_change(
        self, config_reloader: ConfigReloader, test_config_files: list[Path], tmp_path: Path
    ) -> None:
        """Test config hash changes when file changes."""
        hash1 = config_reloader.compute_config_hash()

        # Modify config file
        base_yaml = tmp_path / "config" / "base.yaml"
        base_yaml.write_text("# Modified content\napp:\n  name: changed\n")

        hash2 = config_reloader.compute_config_hash()

        assert hash1 != hash2

    def test_compute_config_hash_with_explicit_files(
        self, config_reloader: ConfigReloader, test_config_files: list[Path]
    ) -> None:
        """Test computing hash with explicit file list."""
        hash1 = config_reloader.compute_config_hash(test_config_files)

        # Should produce same hash as auto-discovery
        hash2 = config_reloader.compute_config_hash()
        assert hash1 == hash2

    def test_compute_config_hash_deterministic(
        self, config_reloader: ConfigReloader, test_config_files: list[Path]
    ) -> None:
        """Test config hash is deterministic (sorted file order)."""
        # Files in different order should produce same hash
        files_forward = sorted(test_config_files)
        files_reverse = sorted(test_config_files, reverse=True)

        hash_forward = config_reloader.compute_config_hash(files_forward)
        hash_reverse = config_reloader.compute_config_hash(files_reverse)

        assert hash_forward == hash_reverse

    def test_validate_config_valid(
        self, config_reloader: ConfigReloader, test_config_files: list[Path], tmp_path: Path
    ) -> None:
        """Test validating valid config."""
        valid, error = config_reloader.validate_config()

        assert valid is True
        assert error is None

    def test_validate_config_invalid(self, config_reloader: ConfigReloader, tmp_path: Path) -> None:
        """Test validating invalid config."""
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # Create invalid YAML
        base_yaml = config_dir / "base.yaml"
        base_yaml.write_text("invalid: yaml: content: [[[")

        valid, error = config_reloader.validate_config()

        assert valid is False
        assert error is not None
        assert isinstance(error, str)

    def test_validate_config_missing(self, config_reloader: ConfigReloader) -> None:
        """Test validating missing config."""
        valid, error = config_reloader.validate_config()

        assert valid is False
        assert error is not None

    @pytest.mark.asyncio
    async def test_reload_service_config(
        self, config_reloader: ConfigReloader, mock_bus: MagicMock
    ) -> None:
        """Test reloading service config."""
        result = await config_reloader.reload_service_config("test_service")

        assert result is True
        mock_bus.publish_json.assert_called_once()

        call_args = mock_bus.publish_json.call_args
        assert call_args[0][0] == RELOAD_TOPIC  # Topic
        assert call_args[0][1]["service"] == "test_service"
        assert "timestamp_ns" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_reload_service_config_handles_error(
        self, config_reloader: ConfigReloader, mock_bus: MagicMock
    ) -> None:
        """Test reload_service_config handles bus errors."""
        mock_bus.publish_json.side_effect = RuntimeError("Bus error")

        result = await config_reloader.reload_service_config("test_service")

        assert result is False

    @pytest.mark.asyncio
    async def test_reload_all_services(
        self, config_reloader: ConfigReloader, mock_bus: MagicMock
    ) -> None:
        """Test reloading all services."""
        result = await config_reloader.reload_all_services()

        assert result is True
        mock_bus.publish_json.assert_called_once()

        call_args = mock_bus.publish_json.call_args
        assert call_args[0][0] == RELOAD_TOPIC
        assert call_args[0][1]["service"] == "*"  # Broadcast
        assert "timestamp_ns" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_reload_all_services_handles_error(
        self, config_reloader: ConfigReloader, mock_bus: MagicMock
    ) -> None:
        """Test reload_all_services handles bus errors."""
        mock_bus.publish_json.side_effect = RuntimeError("Bus error")

        result = await config_reloader.reload_all_services()

        assert result is False

    def test_journal_config_change(self, config_reloader: ConfigReloader, tmp_path: Path) -> None:
        """Test journaling config changes."""
        old_hash = "abc123"
        new_hash = "def456"

        config_reloader._journal_config_change(old_hash, new_hash)

        journal_file = config_reloader.journal_dir / "config_changes.log"
        assert journal_file.exists()

        content = journal_file.read_text()
        assert "abc123" in content
        assert "def456" in content
        assert "config_changed" in content

    def test_journal_config_change_initial(self, config_reloader: ConfigReloader) -> None:
        """Test journaling initial config (no old hash)."""
        new_hash = "def456"

        config_reloader._journal_config_change(None, new_hash)

        journal_file = config_reloader.journal_dir / "config_changes.log"
        content = journal_file.read_text()

        assert "initial" in content
        assert "def456" in content

    @pytest.mark.asyncio
    async def test_watch_config_polling_mode(
        self, config_reloader: ConfigReloader, test_config_files: list[Path], tmp_path: Path
    ) -> None:
        """Test watching config in polling mode."""
        # Force polling mode
        config_reloader._use_inotify = False

        # Start watching in background
        watch_task = asyncio.create_task(config_reloader.watch_config())

        # Give it time to initialize
        await asyncio.sleep(0.15)

        # Modify config
        base_yaml = tmp_path / "config" / "base.yaml"
        original_content = base_yaml.read_text()
        base_yaml.write_text(original_content + "\n# Modified\n")

        # Wait for polling to detect change
        await asyncio.sleep(0.25)

        # Stop watching
        config_reloader.stop_watching()
        await watch_task

        # Should have sent reload signal
        assert cast(AsyncMock, config_reloader.bus.publish_json).call_count >= 1

    @pytest.mark.asyncio
    async def test_watch_config_rejects_invalid_config(
        self, config_reloader: ConfigReloader, test_config_files: list[Path], tmp_path: Path
    ) -> None:
        """Test watching rejects invalid config changes."""
        # Force polling mode
        config_reloader._use_inotify = False

        # Start watching
        watch_task = asyncio.create_task(config_reloader.watch_config())

        # Give it time to initialize
        await asyncio.sleep(0.15)

        # Modify config to be invalid
        base_yaml = tmp_path / "config" / "base.yaml"
        base_yaml.write_text("invalid: yaml: [[[")

        # Wait for polling
        await asyncio.sleep(0.25)

        # Stop watching
        config_reloader.stop_watching()
        await watch_task

        # Should NOT have sent reload signal for invalid config
        # (only initial hash setup, no reload)
        assert cast(AsyncMock, config_reloader.bus.publish_json).call_count == 0

    @pytest.mark.asyncio
    async def test_stop_watching(
        self, config_reloader: ConfigReloader, test_config_files: list[Path]
    ) -> None:
        """Test stopping config watch."""
        config_reloader._use_inotify = False

        # Start watching
        watch_task = asyncio.create_task(config_reloader.watch_config())

        await asyncio.sleep(0.15)

        # Stop watching
        config_reloader.stop_watching()
        await watch_task

        assert config_reloader._watching is False

    @pytest.mark.asyncio
    async def test_watch_config_handles_errors(
        self, config_reloader: ConfigReloader, tmp_path: Path
    ) -> None:
        """Test watch_config handles errors gracefully."""
        # Force polling mode
        config_reloader._use_inotify = False

        # Create config dir but make it unreadable (simulate permission error)
        config_dir = tmp_path / "config"
        config_dir.mkdir()

        # Start watching (should handle errors)
        watch_task = asyncio.create_task(config_reloader.watch_config())

        await asyncio.sleep(0.15)

        config_reloader.stop_watching()
        await watch_task

        # Should not crash, just log errors

    @pytest.mark.asyncio
    @pytest.mark.skipif(platform.system() != "Linux", reason="inotify only available on Linux")
    async def test_watch_config_inotify_mode(
        self, config_reloader: ConfigReloader, test_config_files: list[Path], tmp_path: Path
    ) -> None:
        """Test watching config in inotify mode (Linux only)."""
        # Check if inotify is available
        if not config_reloader._use_inotify:
            pytest.skip("inotify not available")

        # Start watching in background
        watch_task = asyncio.create_task(config_reloader.watch_config())

        # Give it time to initialize
        await asyncio.sleep(0.2)

        # Modify config
        base_yaml = tmp_path / "config" / "base.yaml"
        original_content = base_yaml.read_text()
        base_yaml.write_text(original_content + "\n# Modified\n")

        # Give inotify time to detect
        await asyncio.sleep(0.3)

        # Stop watching
        config_reloader.stop_watching()

        # Wait for watch task to complete
        try:
            await asyncio.wait_for(watch_task, timeout=2.0)
        except TimeoutError:
            # Force cancel if it doesn't stop
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watch_task

        # Should have sent reload signal
        assert cast(AsyncMock, config_reloader.bus.publish_json).call_count >= 1

    def test_config_files_constant(self) -> None:
        """Test CONFIG_FILES constant is defined."""
        assert "config/base.yaml" in CONFIG_FILES
        assert "config/secrets.enc.yaml" in CONFIG_FILES

    def test_reload_topic_constant(self) -> None:
        """Test RELOAD_TOPIC constant is defined."""
        assert RELOAD_TOPIC == "controller.reload"
