"""Tests for metrics dashboard."""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from apps.metrics_dashboard.main import MetricsDashboard
from telemetry.registry import MetricRegistry
from tests.utils import InMemoryBus


async def _make_http_request(
    host: str, port: int, path: str, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, str], str]:
    """Make HTTP request to dashboard.

    Args:
        host: Server host
        port: Server port
        path: Request path
        headers: Optional headers

    Returns:
        (status_code, response_headers, body) tuple
    """
    reader, writer = await asyncio.open_connection(host, port)

    try:
        # Send HTTP request
        request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
        if headers:
            for key, value in headers.items():
                request += f"{key}: {value}\r\n"
        request += "\r\n"

        writer.write(request.encode())
        await writer.drain()

        # Read status line
        status_line = await reader.readline()
        status_parts = status_line.decode().strip().split()
        status_code = int(status_parts[1]) if len(status_parts) > 1 else 500

        # Read headers
        response_headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if line == b"\r\n":
                break
            header_str = line.decode().strip()
            if ":" in header_str:
                key, value = header_str.split(":", 1)
                response_headers[key.strip().lower()] = value.strip()

        # Read body
        content_length = int(response_headers.get("content-length", "0"))
        body = ""
        if content_length > 0:
            body_bytes = await reader.read(content_length)
            body = body_bytes.decode()

        return (status_code, response_headers, body)

    finally:
        writer.close()
        await writer.wait_closed()


class TestMetricsDashboard:
    """Tests for MetricsDashboard server."""

    @pytest.mark.asyncio
    async def test_dashboard_initialization(self) -> None:
        """Test dashboard initialization."""
        bus = InMemoryBus()
        registry = MetricRegistry()

        dashboard = MetricsDashboard(
            bus=bus,
            port=8081,
            bind_host="127.0.0.1",
            registry=registry,
        )

        assert dashboard.port == 8081
        assert dashboard.bind_host == "127.0.0.1"
        assert dashboard.registry is registry

    @pytest.mark.asyncio
    async def test_dashboard_starts_and_stops(self) -> None:
        """Test dashboard server starts and stops cleanly."""
        bus = InMemoryBus()
        dashboard = MetricsDashboard(bus=bus, port=8082)

        await dashboard.start()
        assert dashboard._server is not None

        await dashboard.stop()
        assert dashboard._server is None

    @pytest.mark.asyncio
    async def test_dashboard_binds_to_localhost_by_default(self) -> None:
        """Test dashboard binds to localhost (127.0.0.1) by default."""
        bus = InMemoryBus()
        dashboard = MetricsDashboard(bus=bus, port=8083)

        assert dashboard.bind_host == "127.0.0.1"

        await dashboard.start()
        await dashboard.stop()

    @pytest.mark.asyncio
    async def test_dashboard_accessible_at_root(self) -> None:
        """Test dashboard is accessible at / endpoint."""
        bus = InMemoryBus()
        dashboard = MetricsDashboard(bus=bus, port=8084)

        await dashboard.start()

        try:
            status, headers, body = await _make_http_request("127.0.0.1", 8084, "/")

            assert status == 200
            assert headers["content-type"] == "text/html; charset=utf-8"
            assert "Njord Quant Dashboard" in body
            assert "<html" in body
        finally:
            await dashboard.stop()

    @pytest.mark.asyncio
    async def test_dashboard_metrics_endpoint(self) -> None:
        """Test /api/metrics endpoint returns JSON."""
        bus = InMemoryBus()
        registry = MetricRegistry()
        dashboard = MetricsDashboard(bus=bus, port=8085, registry=registry)

        await dashboard.start()

        try:
            status, headers, body = await _make_http_request("127.0.0.1", 8085, "/api/metrics")

            assert status == 200
            assert headers["content-type"] == "application/json; charset=utf-8"

            data = json.loads(body)
            assert "timestamp" in data
            assert "portfolio" in data
            assert "strategies" in data
            assert "risk" in data
            assert "activity" in data
            assert "system" in data
        finally:
            await dashboard.stop()

    @pytest.mark.asyncio
    async def test_dashboard_metrics_include_portfolio_data(self) -> None:
        """Test metrics endpoint includes portfolio summary."""
        bus = InMemoryBus()
        registry = MetricRegistry()
        dashboard = MetricsDashboard(bus=bus, port=8086, registry=registry)

        # Register and set some metrics
        gauge = await registry.register_gauge(
            "njord_strategy_pnl_usd", "Strategy PnL", ["strategy_id"]
        )
        gauge.set(100.5, {"strategy_id": "alpha"})

        await dashboard.start()

        try:
            status, _headers, body = await _make_http_request("127.0.0.1", 8086, "/api/metrics")

            assert status == 200
            data = json.loads(body)

            assert data["portfolio"]["daily_pnl"] == 100.5
            assert len(data["strategies"]) == 1
            assert data["strategies"][0]["id"] == "alpha"
            assert data["strategies"][0]["pnl"] == 100.5
        finally:
            await dashboard.stop()

    @pytest.mark.asyncio
    async def test_dashboard_404_for_unknown_path(self) -> None:
        """Test dashboard returns 404 for unknown paths."""
        bus = InMemoryBus()
        dashboard = MetricsDashboard(bus=bus, port=8087)

        await dashboard.start()

        try:
            status, _headers, body = await _make_http_request("127.0.0.1", 8087, "/nonexistent")

            assert status == 404
            assert body == "Not Found"
        finally:
            await dashboard.stop()

    @pytest.mark.asyncio
    async def test_dashboard_auth_enforced_with_token(self) -> None:
        """Test Bearer token authentication is enforced when configured."""
        # Set environment variable
        os.environ["NJORD_DASHBOARD_TOKEN"] = "test_secret_token"

        try:
            bus = InMemoryBus()
            dashboard = MetricsDashboard(bus=bus, port=8088)

            await dashboard.start()

            try:
                # Request without auth should fail
                status, _headers, body = await _make_http_request("127.0.0.1", 8088, "/")
                assert status == 401
                assert body == "Unauthorized"

                # Request with correct auth should succeed
                status, _headers, body = await _make_http_request(
                    "127.0.0.1",
                    8088,
                    "/",
                    headers={"Authorization": "Bearer test_secret_token"},
                )
                assert status == 200
                assert "Njord Quant Dashboard" in body

                # Request with incorrect auth should fail
                status, _headers, body = await _make_http_request(
                    "127.0.0.1",
                    8088,
                    "/",
                    headers={"Authorization": "Bearer wrong_token"},
                )
                assert status == 401
                assert body == "Unauthorized"
            finally:
                await dashboard.stop()
        finally:
            # Clean up environment variable
            del os.environ["NJORD_DASHBOARD_TOKEN"]

    @pytest.mark.asyncio
    async def test_dashboard_no_auth_without_token(self) -> None:
        """Test dashboard does not require auth when token not configured."""
        # Ensure token is not set
        if "NJORD_DASHBOARD_TOKEN" in os.environ:
            del os.environ["NJORD_DASHBOARD_TOKEN"]

        bus = InMemoryBus()
        dashboard = MetricsDashboard(bus=bus, port=8089)

        await dashboard.start()

        try:
            # Request without auth should succeed
            status, _headers, body = await _make_http_request("127.0.0.1", 8089, "/")
            assert status == 200
            assert "Njord Quant Dashboard" in body
        finally:
            await dashboard.stop()

    @pytest.mark.asyncio
    async def test_dashboard_renders_html_template(self) -> None:
        """Test dashboard renders complete HTML template."""
        bus = InMemoryBus()
        dashboard = MetricsDashboard(bus=bus)

        html = dashboard.render_dashboard()

        # Check for essential HTML elements
        assert "<!DOCTYPE html>" in html
        assert '<html lang="en">' in html
        assert "<title>Njord Quant Dashboard</title>" in html
        assert "<style>" in html  # Embedded CSS
        assert "<script>" in html  # Embedded JS
        assert "Portfolio Summary" in html
        assert "Strategy Performance" in html
        assert "Risk Status" in html
        assert "System Health" in html
        assert "EventSource" in html  # SSE client code

    @pytest.mark.asyncio
    async def test_dashboard_html_is_mobile_responsive(self) -> None:
        """Test dashboard HTML includes mobile-responsive viewport."""
        bus = InMemoryBus()
        dashboard = MetricsDashboard(bus=bus)

        html = dashboard.render_dashboard()

        assert '<meta name="viewport" content="width=device-width, initial-scale=1.0">' in html
        assert "@media (max-width: 768px)" in html  # Mobile media query

    @pytest.mark.asyncio
    async def test_dashboard_no_external_dependencies(self) -> None:
        """Test dashboard HTML has no external JS/CSS dependencies."""
        bus = InMemoryBus()
        dashboard = MetricsDashboard(bus=bus)

        html = dashboard.render_dashboard()

        # Should not have external script/style tags
        assert '<script src="http' not in html
        assert "<script src=" not in html or "<script>" in html
        assert "<link" not in html or '<link rel="stylesheet"' not in html

        # Should have embedded styles and scripts
        assert "<style>" in html
        assert "<script>" in html

    @pytest.mark.asyncio
    async def test_metrics_include_system_health(self) -> None:
        """Test metrics include system health data."""
        bus = InMemoryBus()
        registry = MetricRegistry()
        dashboard = MetricsDashboard(bus=bus, port=8090, registry=registry)

        # Set system health metrics
        lag_gauge = await registry.register_gauge("njord_event_loop_lag_seconds", "Event loop lag")
        lag_gauge.set(0.015, None)

        memory_gauge = await registry.register_gauge("njord_memory_usage_mb", "Memory usage")
        memory_gauge.set(128.5, None)

        await dashboard.start()

        try:
            status, _headers, body = await _make_http_request("127.0.0.1", 8090, "/api/metrics")

            assert status == 200
            data = json.loads(body)

            assert data["system"]["event_loop_lag_ms"] == 15.0  # 0.015 seconds = 15 ms
            assert data["system"]["memory_usage_mb"] == 128.5
        finally:
            await dashboard.stop()

    @pytest.mark.asyncio
    async def test_metrics_include_strategy_performance(self) -> None:
        """Test metrics include strategy performance data."""
        bus = InMemoryBus()
        registry = MetricRegistry()
        dashboard = MetricsDashboard(bus=bus, port=8091, registry=registry)

        # Set strategy metrics
        pnl_gauge = await registry.register_gauge(
            "njord_strategy_pnl_usd", "Strategy PnL", ["strategy_id"]
        )
        pnl_gauge.set(250.0, {"strategy_id": "alpha"})
        pnl_gauge.set(-50.0, {"strategy_id": "beta"})

        sharpe_gauge = await registry.register_gauge(
            "njord_strategy_sharpe_ratio", "Sharpe ratio", ["strategy_id"]
        )
        sharpe_gauge.set(1.5, {"strategy_id": "alpha"})
        sharpe_gauge.set(0.8, {"strategy_id": "beta"})

        win_rate_gauge = await registry.register_gauge(
            "njord_strategy_win_rate", "Win rate", ["strategy_id"]
        )
        win_rate_gauge.set(0.65, {"strategy_id": "alpha"})
        win_rate_gauge.set(0.45, {"strategy_id": "beta"})

        await dashboard.start()

        try:
            status, _headers, body = await _make_http_request("127.0.0.1", 8091, "/api/metrics")

            assert status == 200
            data = json.loads(body)

            # Portfolio PnL should be sum of strategy PnLs
            assert data["portfolio"]["daily_pnl"] == 200.0  # 250 - 50

            # Check strategies
            assert len(data["strategies"]) == 2

            # Find alpha strategy
            alpha = next(s for s in data["strategies"] if s["id"] == "alpha")
            assert alpha["pnl"] == 250.0
            assert alpha["sharpe"] == 1.5
            assert alpha["win_rate"] == 0.65

            # Find beta strategy
            beta = next(s for s in data["strategies"] if s["id"] == "beta")
            assert beta["pnl"] == -50.0
            assert beta["sharpe"] == 0.8
            assert beta["win_rate"] == 0.45
        finally:
            await dashboard.stop()

    @pytest.mark.asyncio
    async def test_metrics_include_activity_counters(self) -> None:
        """Test metrics include order/fill activity counters."""
        bus = InMemoryBus()
        registry = MetricRegistry()
        dashboard = MetricsDashboard(bus=bus, port=8092, registry=registry)

        # Set activity counters
        orders_counter = await registry.register_counter(
            "njord_orders_placed_total", "Orders placed"
        )
        orders_counter.inc(15, None)

        fills_counter = await registry.register_counter(
            "njord_fills_generated_total", "Fills generated"
        )
        fills_counter.inc(12, None)

        await dashboard.start()

        try:
            status, _headers, body = await _make_http_request("127.0.0.1", 8092, "/api/metrics")

            assert status == 200
            data = json.loads(body)

            assert data["activity"]["total_orders"] == 15
            assert data["activity"]["total_fills"] == 12
        finally:
            await dashboard.stop()

    @pytest.mark.asyncio
    async def test_sse_stream_endpoint(self) -> None:
        """Test SSE stream endpoint sends events."""
        bus = InMemoryBus()
        registry = MetricRegistry()
        dashboard = MetricsDashboard(bus=bus, port=8093, registry=registry)

        await dashboard.start()

        try:
            # Connect to SSE endpoint
            reader, writer = await asyncio.open_connection("127.0.0.1", 8093)

            try:
                # Send HTTP request for SSE
                request = "GET /api/stream HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n"
                writer.write(request.encode())
                await writer.drain()

                # Read status line
                status_line = await reader.readline()
                assert b"200 OK" in status_line

                # Read headers
                headers_read = False
                while not headers_read:
                    line = await reader.readline()
                    if line == b"\r\n":
                        headers_read = True
                    elif b"content-type" in line.lower():
                        assert b"text/event-stream" in line.lower()

                # Read first SSE event with timeout
                try:
                    event_line = await asyncio.wait_for(reader.readline(), timeout=2.0)
                    assert b"data:" in event_line

                    # Parse JSON data
                    data_str = event_line.decode().replace("data: ", "").strip()
                    data = json.loads(data_str)
                    assert "timestamp" in data
                    assert "portfolio" in data
                except TimeoutError:
                    pytest.fail("Timeout waiting for SSE event")

            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await dashboard.stop()

    @pytest.mark.asyncio
    async def test_dashboard_handles_concurrent_requests(self) -> None:
        """Test dashboard handles multiple concurrent requests."""
        bus = InMemoryBus()
        dashboard = MetricsDashboard(bus=bus, port=8094)

        await dashboard.start()

        try:
            # Make multiple concurrent requests
            tasks = [
                _make_http_request("127.0.0.1", 8094, "/"),
                _make_http_request("127.0.0.1", 8094, "/api/metrics"),
                _make_http_request("127.0.0.1", 8094, "/"),
            ]

            results = await asyncio.gather(*tasks)

            # All requests should succeed
            for status, _headers, _body in results:
                assert status == 200
        finally:
            await dashboard.stop()
