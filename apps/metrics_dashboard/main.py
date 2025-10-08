"""Real-time metrics dashboard HTTP server."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.bus import Bus
from core.config import load_config
from core.logging import setup_json_logging
from telemetry.registry import MetricRegistry

if TYPE_CHECKING:
    from core.bus import BusProto

logger = logging.getLogger(__name__)


class MetricsDashboard:
    """Real-time web-based metrics dashboard.

    Serves a lightweight HTML dashboard with real-time metric updates
    using Server-Sent Events (SSE).
    """

    def __init__(
        self,
        bus: BusProto,
        port: int = 8080,
        bind_host: str = "127.0.0.1",
        registry: MetricRegistry | None = None,
    ) -> None:
        """Initialize metrics dashboard.

        Args:
            bus: Event bus instance
            port: HTTP port to bind to
            bind_host: Host to bind to (defaults to localhost for security)
            registry: Metric registry (creates new if None)
        """
        self.bus = bus
        self.port = port
        self.bind_host = bind_host
        self.registry = registry or MetricRegistry()
        self._server: asyncio.Server | None = None
        self._bearer_token = os.getenv("NJORD_DASHBOARD_TOKEN")
        self._logger = logging.getLogger(__name__)
        self._sse_clients: set[asyncio.StreamWriter] = set()

    async def start(self) -> None:
        """Start HTTP server for dashboard.

        Security:
            - Binds to localhost (127.0.0.1) by default
            - Optional Bearer token auth via NJORD_DASHBOARD_TOKEN env var
        """
        self._server = await asyncio.start_server(self._handle_client, self.bind_host, self.port)
        self._logger.info(
            "dashboard_started",
            extra={
                "bind_host": self.bind_host,
                "port": self.port,
                "auth_enabled": bool(self._bearer_token),
            },
        )

    async def stop(self) -> None:
        """Stop HTTP server."""
        # Close all SSE connections
        for writer in list(self._sse_clients):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self._sse_clients.clear()

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle HTTP client connection."""
        try:
            # Read HTTP request line
            request_line = await reader.readline()
            if not request_line:
                return

            request_str = request_line.decode("utf-8").strip()
            parts = request_str.split()
            if len(parts) < 2:
                await self._send_response(writer, 400, "Bad Request")
                return

            method, path = parts[0], parts[1]

            # Read headers
            headers = await self._read_headers(reader)

            # Check authentication if token is configured
            if self._bearer_token:
                auth_header = headers.get("authorization", "")
                expected_auth = f"Bearer {self._bearer_token}"
                if auth_header != expected_auth:
                    await self._send_response(writer, 401, "Unauthorized")
                    return

            # Route request
            if method == "GET" and path == "/":
                html = self.render_dashboard()
                await self._send_response(writer, 200, html, content_type="text/html")
            elif method == "GET" and path == "/api/metrics":
                metrics = await self._get_current_metrics()
                body = json.dumps(metrics)
                await self._send_response(writer, 200, body, content_type="application/json")
            elif method == "GET" and path == "/api/stream":
                await self._handle_sse(writer)
            else:
                await self._send_response(writer, 404, "Not Found")

        except Exception:
            self._logger.exception("dashboard_request_error")
            with contextlib.suppress(Exception):
                await self._send_response(writer, 500, "Internal Server Error")
        finally:
            if writer not in self._sse_clients:
                with contextlib.suppress(Exception):
                    writer.close()
                    await writer.wait_closed()

    async def _read_headers(self, reader: asyncio.StreamReader) -> dict[str, str]:
        """Read HTTP headers."""
        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if not line or line == b"\r\n":
                break

            header_str = line.decode("utf-8").strip()
            if ":" in header_str:
                key, value = header_str.split(":", 1)
                headers[key.strip().lower()] = value.strip()

        return headers

    async def _send_response(
        self,
        writer: asyncio.StreamWriter,
        status_code: int,
        body: str,
        content_type: str = "text/plain",
    ) -> None:
        """Send HTTP response."""
        status_messages = {
            200: "OK",
            400: "Bad Request",
            401: "Unauthorized",
            404: "Not Found",
            500: "Internal Server Error",
        }
        status_message = status_messages.get(status_code, "Unknown")

        response = (
            f"HTTP/1.1 {status_code} {status_message}\r\n"
            f"Content-Type: {content_type}; charset=utf-8\r\n"
            f"Content-Length: {len(body.encode('utf-8'))}\r\n"
            f"Connection: close\r\n"
            f"\r\n"
            f"{body}"
        )

        writer.write(response.encode("utf-8"))
        await writer.drain()

    async def _handle_sse(self, writer: asyncio.StreamWriter) -> None:
        """Handle Server-Sent Events connection for real-time updates."""
        # Send SSE headers
        headers = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/event-stream\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: keep-alive\r\n"
            "\r\n"
        )
        writer.write(headers.encode("utf-8"))
        await writer.drain()

        # Register client
        self._sse_clients.add(writer)

        try:
            # Send metrics every second
            while True:
                metrics = await self._get_current_metrics()
                event_data = f"data: {json.dumps(metrics)}\n\n"
                writer.write(event_data.encode("utf-8"))
                await writer.drain()
                await asyncio.sleep(1.0)
        except Exception:
            pass
        finally:
            self._sse_clients.discard(writer)

    async def _get_current_metrics(self) -> dict[str, Any]:
        """Get current metrics snapshot."""
        all_metrics = self.registry.collect_all()

        # Portfolio summary
        portfolio_pnl = 0.0
        position_count = 0
        equity = 0.0

        # Strategy performance
        strategies: dict[str, dict[str, Any]] = {}

        # System health
        event_loop_lag = 0.0
        memory_usage_mb = 0.0

        # Extract metrics from registry
        for name, gauge in all_metrics["gauges"].items():
            samples = gauge.collect()
            for labels_dict, value in samples:
                if name == "njord_strategy_pnl_usd":
                    strategy_id = labels_dict.get("strategy_id", "unknown")
                    if strategy_id not in strategies:
                        strategies[strategy_id] = {"pnl": 0.0, "sharpe": 0.0, "win_rate": 0.0}
                    strategies[strategy_id]["pnl"] = value
                    portfolio_pnl += value
                elif name == "njord_position_size":
                    position_count += 1
                elif name == "njord_event_loop_lag_seconds":
                    event_loop_lag = value
                elif name == "njord_memory_usage_mb":
                    memory_usage_mb += value
                elif name == "njord_strategy_sharpe_ratio":
                    strategy_id = labels_dict.get("strategy_id", "unknown")
                    if strategy_id not in strategies:
                        strategies[strategy_id] = {"pnl": 0.0, "sharpe": 0.0, "win_rate": 0.0}
                    strategies[strategy_id]["sharpe"] = value
                elif name == "njord_strategy_win_rate":
                    strategy_id = labels_dict.get("strategy_id", "unknown")
                    if strategy_id not in strategies:
                        strategies[strategy_id] = {"pnl": 0.0, "sharpe": 0.0, "win_rate": 0.0}
                    strategies[strategy_id]["win_rate"] = value

        # Recent activity from counters
        total_orders = 0
        total_fills = 0
        for name, counter in all_metrics["counters"].items():
            samples = counter.collect()
            for _labels_dict, value in samples:
                if name == "njord_orders_placed_total":
                    total_orders += int(value)
                elif name == "njord_fills_generated_total":
                    total_fills += int(value)

        return {
            "timestamp": int(time.time() * 1000),
            "portfolio": {
                "equity": equity,
                "daily_pnl": portfolio_pnl,
                "position_count": position_count,
            },
            "strategies": [{"id": sid, **data} for sid, data in sorted(strategies.items())],
            "risk": {
                "killswitch_active": False,
                "caps_utilization": 0.0,
            },
            "activity": {
                "total_orders": total_orders,
                "total_fills": total_fills,
            },
            "system": {
                "event_loop_lag_ms": event_loop_lag * 1000,
                "memory_usage_mb": memory_usage_mb,
            },
        }

    def render_dashboard(self) -> str:
        """Render dashboard HTML with embedded CSS and JS."""
        return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Njord Quant Dashboard</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0a0e17;
            color: #e4e6eb;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        h1 {
            font-size: 2rem;
            margin-bottom: 0.5rem;
            color: #00d4ff;
        }
        .last-update {
            font-size: 0.875rem;
            color: #8b92a7;
            margin-bottom: 1.5rem;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1rem;
            margin-bottom: 1rem;
        }
        .card {
            background: #161b2e;
            border-radius: 8px;
            padding: 1.5rem;
            border: 1px solid #1e2738;
        }
        .card-title {
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #8b92a7;
            margin-bottom: 1rem;
        }
        .metric {
            margin-bottom: 0.75rem;
        }
        .metric-label {
            font-size: 0.875rem;
            color: #8b92a7;
            margin-bottom: 0.25rem;
        }
        .metric-value {
            font-size: 1.5rem;
            font-weight: 600;
        }
        .positive {
            color: #10b981;
        }
        .negative {
            color: #ef4444;
        }
        .neutral {
            color: #e4e6eb;
        }
        .strategy-item {
            background: #1a2035;
            padding: 0.75rem;
            border-radius: 6px;
            margin-bottom: 0.5rem;
            border-left: 3px solid #00d4ff;
        }
        .strategy-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.5rem;
        }
        .strategy-name {
            font-weight: 600;
            color: #00d4ff;
        }
        .strategy-metrics {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 0.5rem;
            font-size: 0.75rem;
        }
        .strategy-metrics div {
            text-align: center;
        }
        .status-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 0.5rem;
        }
        .status-ok {
            background: #10b981;
        }
        .status-warning {
            background: #f59e0b;
        }
        .status-error {
            background: #ef4444;
        }
        @media (max-width: 768px) {
            .grid {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Njord Quant Dashboard</h1>
        <div class="last-update">Last updated: <span id="lastUpdate">--</span></div>

        <div class="grid">
            <div class="card">
                <div class="card-title">Portfolio Summary</div>
                <div class="metric">
                    <div class="metric-label">Equity</div>
                    <div class="metric-value neutral" id="equity">$0.00</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Daily P&L</div>
                    <div class="metric-value neutral" id="dailyPnl">$0.00</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Positions</div>
                    <div class="metric-value neutral" id="positionCount">0</div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">Risk Status</div>
                <div class="metric">
                    <div class="metric-label">Kill Switch</div>
                    <div class="metric-value" id="killswitch">
                        <span class="status-indicator status-ok"></span>
                        <span>Active</span>
                    </div>
                </div>
                <div class="metric">
                    <div class="metric-label">Caps Utilization</div>
                    <div class="metric-value neutral" id="capsUtil">0%</div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">Recent Activity</div>
                <div class="metric">
                    <div class="metric-label">Total Orders</div>
                    <div class="metric-value neutral" id="totalOrders">0</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Total Fills</div>
                    <div class="metric-value neutral" id="totalFills">0</div>
                </div>
            </div>

            <div class="card">
                <div class="card-title">System Health</div>
                <div class="metric">
                    <div class="metric-label">Event Loop Lag</div>
                    <div class="metric-value neutral" id="eventLoopLag">0.0 ms</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Memory Usage</div>
                    <div class="metric-value neutral" id="memoryUsage">0 MB</div>
                </div>
            </div>
        </div>

        <div class="card">
            <div class="card-title">Strategy Performance</div>
            <div id="strategies">
                <div style="text-align: center; color: #8b92a7; padding: 2rem;">
                    No strategies active
                </div>
            </div>
        </div>
    </div>

    <script>
        // Connect to SSE endpoint
        const eventSource = new EventSource('/api/stream');

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            updateDashboard(data);
        };

        eventSource.onerror = function() {
            document.getElementById('lastUpdate').textContent = 'Connection lost';
        };

        function updateDashboard(data) {
            // Update timestamp
            const date = new Date(data.timestamp);
            document.getElementById('lastUpdate').textContent = date.toLocaleTimeString();

            // Portfolio
            const pnl = data.portfolio.daily_pnl;
            document.getElementById('equity').textContent = '$' + data.portfolio.equity.toFixed(2);
            document.getElementById('dailyPnl').textContent = formatPnL(pnl);
            document.getElementById('dailyPnl').className = 'metric-value ' + getPnLClass(pnl);
            document.getElementById('positionCount').textContent = data.portfolio.position_count;

            // Risk
            const killswitch = data.risk.killswitch_active;
            document.getElementById('killswitch').innerHTML =
                '<span class="status-indicator status-' + (killswitch ? 'error' : 'ok') + '"></span>' +
                '<span>' + (killswitch ? 'Triggered' : 'Active') + '</span>';
            document.getElementById('capsUtil').textContent =
                (data.risk.caps_utilization * 100).toFixed(1) + '%';

            // Activity
            document.getElementById('totalOrders').textContent = data.activity.total_orders;
            document.getElementById('totalFills').textContent = data.activity.total_fills;

            // System
            document.getElementById('eventLoopLag').textContent =
                data.system.event_loop_lag_ms.toFixed(2) + ' ms';
            document.getElementById('memoryUsage').textContent =
                data.system.memory_usage_mb.toFixed(0) + ' MB';

            // Strategies
            updateStrategies(data.strategies);
        }

        function updateStrategies(strategies) {
            const container = document.getElementById('strategies');

            if (!strategies || strategies.length === 0) {
                container.innerHTML = '<div style="text-align: center; color: #8b92a7; padding: 2rem;">No strategies active</div>';
                return;
            }

            container.innerHTML = strategies.map(s => {
                const pnl = s.pnl || 0;
                return `
                    <div class="strategy-item">
                        <div class="strategy-header">
                            <div class="strategy-name">${s.id}</div>
                            <div class="${getPnLClass(pnl)}" style="font-weight: 600;">
                                ${formatPnL(pnl)}
                            </div>
                        </div>
                        <div class="strategy-metrics">
                            <div>
                                <div style="color: #8b92a7;">Sharpe</div>
                                <div>${(s.sharpe || 0).toFixed(2)}</div>
                            </div>
                            <div>
                                <div style="color: #8b92a7;">Win Rate</div>
                                <div>${((s.win_rate || 0) * 100).toFixed(1)}%</div>
                            </div>
                            <div>
                                <div style="color: #8b92a7;">Status</div>
                                <div>Active</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function formatPnL(value) {
            const sign = value >= 0 ? '+' : '';
            return sign + '$' + value.toFixed(2);
        }

        function getPnLClass(value) {
            if (value > 0) return 'positive';
            if (value < 0) return 'negative';
            return 'neutral';
        }
    </script>
</body>
</html>
"""


async def run_dashboard(config_root: str, port: int, bind_host: str) -> None:
    """Run metrics dashboard server.

    Args:
        config_root: Config directory path
        port: HTTP port to bind to
        bind_host: Host to bind to
    """
    config = load_config(config_root)
    log_dir = Path(config.logging.journal_dir)
    setup_json_logging(str(log_dir))

    logger.info(
        "dashboard_starting",
        extra={
            "port": port,
            "bind_host": bind_host,
        },
    )

    # Create shared registry (same one used by other components)
    registry = MetricRegistry()

    # Create bus connection
    bus = Bus(config.redis.url)

    # Create and start dashboard
    dashboard = MetricsDashboard(
        bus=bus,
        port=port,
        bind_host=bind_host,
        registry=registry,
    )

    try:
        await dashboard.start()
        logger.info("dashboard_ready", extra={"url": f"http://{bind_host}:{port}"})

        # Keep running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("dashboard_shutdown")
    finally:
        await dashboard.stop()
        await bus.close()


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser."""
    parser = argparse.ArgumentParser(description="Njord metrics dashboard")
    parser.add_argument(
        "--config-root",
        default=".",
        help="Directory containing config/ (defaults to current working directory)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="HTTP port to bind to (default: 8080)",
    )
    parser.add_argument(
        "--bind-host",
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1 for localhost-only)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        asyncio.run(
            run_dashboard(
                config_root=args.config_root,
                port=args.port,
                bind_host=args.bind_host,
            )
        )
    except KeyboardInterrupt:
        return 0

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
