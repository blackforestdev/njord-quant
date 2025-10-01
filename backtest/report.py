"""Backtest report generator with HTML output."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path


def generate_report(
    strategy_id: str,
    symbol: str,
    metrics: dict[str, float],
    equity_curve: list[tuple[int, float]],
    trades: list[dict[str, object]],
    config: dict[str, float],
    output_path: Path,
) -> None:
    """Generate HTML backtest report.

    Args:
        strategy_id: Strategy identifier
        symbol: Trading symbol
        metrics: Performance metrics dictionary
        equity_curve: List of (timestamp_ns, equity) tuples
        trades: List of trade dictionaries
        config: Backtest configuration
        output_path: Path to output HTML file
    """
    # Prepare data for charts
    timestamps = [ts_ns / 1_000_000_000 for ts_ns, _ in equity_curve]  # Convert to seconds
    equity_values = [equity for _, equity in equity_curve]

    # Calculate drawdown curve
    drawdown_values = _calculate_drawdown_series(equity_curve)

    # Generate HTML
    html = _generate_html(
        strategy_id=strategy_id,
        symbol=symbol,
        metrics=metrics,
        timestamps=timestamps,
        equity_values=equity_values,
        drawdown_values=drawdown_values,
        trades=trades,
        config=config,
    )

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write HTML file
    output_path.write_text(html)


def _calculate_drawdown_series(equity_curve: list[tuple[int, float]]) -> list[float]:
    """Calculate drawdown series from equity curve.

    Args:
        equity_curve: List of (timestamp_ns, equity) tuples

    Returns:
        List of drawdown percentages
    """
    if not equity_curve:
        return []

    drawdowns = []
    peak = equity_curve[0][1]

    for _ts, equity in equity_curve:
        if equity > peak:
            peak = equity

        drawdown = ((peak - equity) / peak) * 100.0 if peak > 0 else 0.0
        drawdowns.append(drawdown)

    return drawdowns


def _generate_html(
    strategy_id: str,
    symbol: str,
    metrics: dict[str, float],
    timestamps: list[float],
    equity_values: list[float],
    drawdown_values: list[float],
    trades: list[dict[str, object]],
    config: dict[str, float],
) -> str:
    """Generate HTML report content.

    Args:
        strategy_id: Strategy identifier
        symbol: Trading symbol
        metrics: Performance metrics
        timestamps: Timestamp series (seconds since epoch)
        equity_values: Equity curve values
        drawdown_values: Drawdown series
        trades: List of trades
        config: Backtest configuration

    Returns:
        HTML string
    """
    # Format timestamps as dates
    date_labels = [datetime.fromtimestamp(ts).strftime("%Y-%m-%d") for ts in timestamps]

    # Generate metrics table HTML
    metrics_html = _generate_metrics_table(metrics)

    # Generate config table HTML
    config_html = _generate_config_table(config)

    # Generate trade distribution
    trade_pnls = _extract_trade_pnls(trades)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Backtest Report: {strategy_id} on {symbol}</title>
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #007bff;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
            border-bottom: 2px solid #ddd;
            padding-bottom: 5px;
        }}
        .chart {{
            background: white;
            padding: 20px;
            margin: 20px 0;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #007bff;
            color: white;
            font-weight: bold;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .metric-value {{
            font-weight: bold;
            color: #007bff;
        }}
        .positive {{
            color: #28a745;
        }}
        .negative {{
            color: #dc3545;
        }}
    </style>
</head>
<body>
    <h1>Backtest Report: {strategy_id} on {symbol}</h1>

    <h2>Performance Metrics</h2>
    {metrics_html}

    <h2>Configuration</h2>
    {config_html}

    <h2>Equity Curve</h2>
    <div id="equityChart" class="chart"></div>

    <h2>Drawdown</h2>
    <div id="drawdownChart" class="chart"></div>

    <h2>Trade Distribution</h2>
    <div id="tradeDistChart" class="chart"></div>

    <script>
        // Equity curve chart
        var equityData = [{{
            x: {date_labels},
            y: {equity_values},
            type: 'scatter',
            mode: 'lines',
            name: 'Equity',
            line: {{
                color: '#007bff',
                width: 2
            }}
        }}];

        var equityLayout = {{
            title: 'Equity Curve',
            xaxis: {{ title: 'Date' }},
            yaxis: {{ title: 'Equity ($)' }},
            hovermode: 'x unified'
        }};

        Plotly.newPlot('equityChart', equityData, equityLayout);

        // Drawdown chart
        var drawdownData = [{{
            x: {date_labels},
            y: {drawdown_values},
            type: 'scatter',
            mode: 'lines',
            name: 'Drawdown',
            fill: 'tozeroy',
            line: {{
                color: '#dc3545',
                width: 2
            }}
        }}];

        var drawdownLayout = {{
            title: 'Drawdown',
            xaxis: {{ title: 'Date' }},
            yaxis: {{ title: 'Drawdown (%)' }},
            hovermode: 'x unified'
        }};

        Plotly.newPlot('drawdownChart', drawdownData, drawdownLayout);

        // Trade distribution chart
        var tradeDistData = [{{
            x: {trade_pnls},
            type: 'histogram',
            marker: {{
                color: '#007bff'
            }}
        }}];

        var tradeDistLayout = {{
            title: 'Trade P&L Distribution',
            xaxis: {{ title: 'P&L ($)' }},
            yaxis: {{ title: 'Frequency' }},
            bargap: 0.1
        }};

        Plotly.newPlot('tradeDistChart', tradeDistData, tradeDistLayout);
    </script>
</body>
</html>"""

    return html


def _generate_metrics_table(metrics: dict[str, float]) -> str:
    """Generate HTML table for performance metrics.

    Args:
        metrics: Performance metrics dictionary

    Returns:
        HTML table string
    """
    rows = []
    for key, value in metrics.items():
        # Format metric name
        display_name = key.replace("_", " ").title()

        # Format value
        if "pct" in key or "rate" in key:
            formatted_value = f"{value:.2f}%"
            css_class = "positive" if value > 0 else "negative"
        elif "ratio" in key or "factor" in key:
            formatted_value = f"{value:.2f}"
            css_class = "positive" if value > 1 else "negative" if value < 1 else ""
        elif isinstance(value, int):
            formatted_value = f"{value:,}"
            css_class = ""
        else:
            formatted_value = f"{value:.2f}"
            css_class = "positive" if value > 0 else "negative" if value < 0 else ""

        rows.append(
            f'<tr><td>{display_name}</td><td class="metric-value {css_class}">{formatted_value}</td></tr>'
        )

    return f"""
    <table>
        <tr>
            <th>Metric</th>
            <th>Value</th>
        </tr>
        {"".join(rows)}
    </table>
    """


def _generate_config_table(config: dict[str, float]) -> str:
    """Generate HTML table for configuration.

    Args:
        config: Configuration dictionary

    Returns:
        HTML table string
    """
    rows = []
    for key, value in config.items():
        display_name = key.replace("_", " ").title()
        formatted_value = f"{value:,.2f}" if isinstance(value, float) else str(value)
        rows.append(f"<tr><td>{display_name}</td><td>{formatted_value}</td></tr>")

    return f"""
    <table>
        <tr>
            <th>Parameter</th>
            <th>Value</th>
        </tr>
        {"".join(rows)}
    </table>
    """


def _extract_trade_pnls(trades: list[dict[str, object]]) -> list[float]:
    """Extract P&L from trades.

    Args:
        trades: List of trade dictionaries

    Returns:
        List of P&L values
    """
    pnls = []
    buy_price = None
    buy_qty = 0.0

    for trade in trades:
        side = trade.get("side")
        price = float(trade.get("price", 0.0))  # type: ignore[arg-type]
        qty = float(trade.get("qty", 0.0))  # type: ignore[arg-type]

        if side == "buy":
            buy_price = price
            buy_qty = qty
        elif side == "sell" and buy_price is not None:
            pnl = (price - buy_price) * min(buy_qty, qty)
            pnls.append(pnl)
            buy_price = None

    # If no trades, return placeholder
    if not pnls:
        pnls = [0.0]

    return pnls
