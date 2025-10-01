from __future__ import annotations

import json
import tempfile
from pathlib import Path

from apps.ohlcv_aggregator.main import MultiTimeframeAggregator
from core.contracts import OHLCVBar


def test_persistence_journals_created() -> None:
    """Test that journal files are created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agg = MultiTimeframeAggregator("ATOM/USDT", ["1m", "5m"], tmpdir)

        assert len(agg.journal_files) == 2
        assert "1m" in agg.journal_files
        assert "5m" in agg.journal_files


def test_persistence_writes_bars() -> None:
    """Test that bars are written to journal files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agg = MultiTimeframeAggregator("ATOM/USDT", ["1m"], tmpdir)

        # Generate a bar
        agg.add_trade(price=10.0, qty=100.0, timestamp_ns=0)
        bars = agg.add_trade(price=11.0, qty=50.0, timestamp_ns=60_000_000_000)

        assert "1m" in bars

        # Check journal file was written
        journal_path = agg.journal_files["1m"]
        assert journal_path.exists()

        # Read and verify content
        with open(journal_path) as f:
            line = f.readline()
            bar_dict = json.loads(line)

            assert bar_dict["symbol"] == "ATOM/USDT"
            assert bar_dict["timeframe"] == "1m"
            assert bar_dict["close"] == 10.0


def test_persistence_ndjson_format() -> None:
    """Test that journal is in NDJSON format (one JSON per line)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agg = MultiTimeframeAggregator("ATOM/USDT", ["1m"], tmpdir)

        # Generate multiple bars
        for minute in range(5):
            timestamp_ns = minute * 60_000_000_000
            agg.add_trade(price=10.0 + minute, qty=100.0, timestamp_ns=timestamp_ns)

        # Close last bar
        agg.add_trade(price=15.0, qty=50.0, timestamp_ns=300_000_000_000)

        # Read journal
        journal_path = agg.journal_files["1m"]
        with open(journal_path) as f:
            lines = f.readlines()

        # Should have 5 bars (minutes 0-4)
        assert len(lines) == 5

        # Each line should be valid JSON
        for line in lines:
            bar_dict = json.loads(line.strip())
            assert "symbol" in bar_dict
            assert "timeframe" in bar_dict


def test_persistence_replay_matches_original() -> None:
    """Test that replay from journal matches original bars."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agg = MultiTimeframeAggregator("ATOM/USDT", ["1m"], tmpdir)

        original_bars: list[OHLCVBar] = []

        # Generate bars and save originals
        for minute in range(10):
            timestamp_ns = minute * 60_000_000_000
            bars = agg.add_trade(price=10.0 + minute, qty=100.0, timestamp_ns=timestamp_ns)

            if "1m" in bars:
                original_bars.append(bars["1m"])

        # Close last bar
        final_bars = agg.add_trade(price=20.0, qty=50.0, timestamp_ns=600_000_000_000)
        if "1m" in final_bars:
            original_bars.append(final_bars["1m"])

        # Read from journal
        journal_path = agg.journal_files["1m"]
        replayed_bars: list[OHLCVBar] = []

        with open(journal_path) as f:
            for line in f:
                bar_dict = json.loads(line.strip())
                bar = OHLCVBar(**bar_dict)
                replayed_bars.append(bar)

        # Compare
        assert len(replayed_bars) == len(original_bars)

        for original, replayed in zip(replayed_bars, original_bars, strict=True):
            assert original == replayed


def test_persistence_multiple_timeframes() -> None:
    """Test journaling for multiple timeframes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agg = MultiTimeframeAggregator("ATOM/USDT", ["1m", "5m"], tmpdir)

        # Generate 6 minutes of trades
        for minute in range(7):
            timestamp_ns = minute * 60_000_000_000
            agg.add_trade(price=10.0 + minute, qty=100.0, timestamp_ns=timestamp_ns)

        # Check both journals exist and have content
        journal_1m = agg.journal_files["1m"]
        journal_5m = agg.journal_files["5m"]

        assert journal_1m.exists()
        assert journal_5m.exists()

        with open(journal_1m) as f:
            lines_1m = f.readlines()

        with open(journal_5m) as f:
            lines_5m = f.readlines()

        # Should have 6 1m bars and 1 5m bar
        assert len(lines_1m) == 6
        assert len(lines_5m) == 1


def test_persistence_flush_after_each_bar() -> None:
    """Test that bars are flushed after each write."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agg = MultiTimeframeAggregator("ATOM/USDT", ["1m"], tmpdir)

        # Generate first bar
        agg.add_trade(price=10.0, qty=100.0, timestamp_ns=0)
        agg.add_trade(price=11.0, qty=50.0, timestamp_ns=60_000_000_000)

        # Journal should be immediately readable
        journal_path = agg.journal_files["1m"]
        with open(journal_path) as f:
            lines = f.readlines()

        assert len(lines) == 1


def test_persistence_correct_paths() -> None:
    """Test that journals are written to correct paths."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agg = MultiTimeframeAggregator("ATOM/USDT", ["1m", "5m"], tmpdir)

        # Check paths
        journal_1m = agg.journal_files["1m"]
        journal_5m = agg.journal_files["5m"]

        expected_1m = Path(tmpdir) / "ohlcv.1m.ATOMUSDT.ndjson"
        expected_5m = Path(tmpdir) / "ohlcv.5m.ATOMUSDT.ndjson"

        assert journal_1m == expected_1m
        assert journal_5m == expected_5m


def test_persistence_symbol_sanitization() -> None:
    """Test that symbol slashes are removed from filename."""
    with tempfile.TemporaryDirectory() as tmpdir:
        agg = MultiTimeframeAggregator("BTC/USDT", ["1m"], tmpdir)

        journal_path = agg.journal_files["1m"]
        assert "BTC/USDT" not in str(journal_path)
        assert "BTCUSDT" in str(journal_path)


def test_persistence_no_journal_dir() -> None:
    """Test that aggregator works without journaling."""
    agg = MultiTimeframeAggregator("ATOM/USDT", ["1m"], journal_dir=None)

    # Should work but not create journals
    agg.add_trade(price=10.0, qty=100.0, timestamp_ns=0)
    bars = agg.add_trade(price=11.0, qty=50.0, timestamp_ns=60_000_000_000)

    assert "1m" in bars
    assert len(agg.journal_files) == 0
