"""Portfolio-level HTML report generator."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from backtest.portfolio_engine import PortfolioBacktestResult


def generate_portfolio_report(
    result: PortfolioBacktestResult,
    per_strategy_metrics: Mapping[str, Mapping[str, float]],
    allocation_history: Sequence[tuple[int, Mapping[str, float]]],
    rebalance_events: Sequence[Mapping[str, object]],
    output_path: Path,
) -> None:
    """Generate an interactive HTML report visualizing portfolio performance."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    equity_ts = [ts for ts, _ in result.equity_curve]
    equity_vals = [equity for _, equity in result.equity_curve]
    allocations_ts = [ts for ts, _ in allocation_history]
    allocations_series = [dict(alloc) for _, alloc in allocation_history]
    rebalance_payload = [dict(event) for event in rebalance_events]

    html = _render_html(
        result=result,
        per_strategy_metrics=per_strategy_metrics,
        equity_timestamps=[_format_timestamp(ts) for ts in equity_ts],
        equity_values=list(equity_vals),
        allocation_timestamps=[_format_timestamp(ts) for ts in allocations_ts],
        allocation_series=allocations_series,
        rebalance_events=rebalance_payload,
    )

    output_path.write_text(html, encoding="utf-8")


def _render_html(
    *,
    result: PortfolioBacktestResult,
    per_strategy_metrics: Mapping[str, Mapping[str, float]],
    equity_timestamps: list[str],
    equity_values: list[float],
    allocation_timestamps: list[str],
    allocation_series: Sequence[Mapping[str, float]],
    rebalance_events: Sequence[Mapping[str, object]],
) -> str:
    metrics_table = _metrics_table(result.metrics)
    strategy_table = _strategy_metrics_table(per_strategy_metrics)
    allocation_payload = [dict(row) for row in allocation_series]
    rebalance_payload = [dict(event) for event in rebalance_events]

    data_json = json.dumps(
        {
            "equity": {
                "timestamps": equity_timestamps,
                "values": equity_values,
            },
            "allocations": {
                "timestamps": allocation_timestamps,
                "series": allocation_payload,
            },
            "rebalances": rebalance_payload,
        }
    )

    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
    <title>Portfolio Report - {result.portfolio_id}</title>
  <script src=\"https://cdn.plot.ly/plotly-2.26.0.min.js\"></script>
  <style>
    body {{ font-family: 'Inter', sans-serif; background: #f6f8fb; color: #222; margin: 0; padding: 0; }}
    header {{ background: #0d47a1; color: white; padding: 20px 40px; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 30px; }}
    section {{ background: white; border-radius: 10px; padding: 24px; margin-bottom: 24px; box-shadow: 0 8px 24px rgba(15,23,42,.08); }}
    h1 {{ font-size: 28px; margin: 0; }}
    h2 {{ margin-top: 0; font-size: 22px; color: #0d47a1; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
    th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e6e9ef; }}
    th {{ background: #f1f5fb; font-weight: 600; }}
    .chart {{ height: 360px; }}
    .meta-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }}
    .meta-card {{ background: #0d47a1; color: white; border-radius: 12px; padding: 18px; }}
    .meta-card span {{ display: block; font-size: 14px; text-transform: uppercase; opacity: .85; margin-bottom: 4px; }}
    .meta-card strong {{ font-size: 24px; letter-spacing: -0.02em; }}
  </style>
</head>
<body>
  <header>
    <h1>Portfolio Report - {result.portfolio_id}</h1>
    <p>Period: {_format_timestamp(result.start_ts)} → {_format_timestamp(result.end_ts)}</p>
  </header>
  <main>
    <section>
      <div class=\"meta-grid\">
        {_meta_card("Final Equity", f"${result.final_capital:,.2f}")}
        {_meta_card("Total Return", f"{result.total_return_pct:.2f}%")}
        {_meta_card("Sharpe Ratio", f"{result.sharpe_ratio:.2f}")}
        {_meta_card("Max Drawdown", f"{result.max_drawdown_pct:.2f}%")}
      </div>
    </section>
    <section>
      <h2>Portfolio Metrics</h2>
      {metrics_table}
    </section>
    <section>
      <h2>Per-Strategy Metrics</h2>
      {strategy_table}
    </section>
    <section>
      <h2>Equity Curve</h2>
      <div id=\"equity-chart\" class=\"chart\"></div>
    </section>
    <section>
      <h2>Allocation History</h2>
      <div id=\"allocation-chart\" class=\"chart\"></div>
    </section>
    <section>
      <h2>Rebalance Events</h2>
      <div id=\"rebalance-table\"></div>
    </section>
  </main>
  <script>
    const DATA = {data_json};
    const strategies = Object.keys(DATA.allocations.series[0] || {{}});

    Plotly.newPlot('equity-chart', [{{
      x: DATA.equity.timestamps,
      y: DATA.equity.values,
      mode: 'lines',
      line: {{ color: '#0d47a1', width: 3 }},
      fill: 'tozeroy',
      name: 'Equity'
    }}], {{
      margin: {{ t: 30, l: 40, r: 20, b: 40 }},
      xaxis: {{ title: 'Date' }},
      yaxis: {{ title: 'Equity (USD)' }},
      paper_bgcolor: 'white',
      plot_bgcolor: '#f5f7fb'
    }});

    const allocation_traces = strategies.map((sid) => ({{
        x: DATA.allocations.timestamps,
        y: DATA.allocations.series.map(row => row[sid] ?? 0),
        stackgroup: 'alloc',
        groupnorm: 'percent',
        name: sid,
        mode: 'lines'
    }}));

    Plotly.newPlot('allocation-chart', allocation_traces, {{
      margin: {{ t: 30, l: 40, r: 20, b: 40 }},
      yaxis: {{ title: 'Allocation (%)' }},
      xaxis: {{ title: 'Date' }},
      paper_bgcolor: 'white',
      plot_bgcolor: '#f5f7fb'
    }});

    const tableContainer = document.getElementById('rebalance-table');
    if (DATA.rebalances.length === 0) {{
      tableContainer.innerHTML = '<p>No rebalance events recorded.</p>';
    }} else {{
      const headers = Object.keys(DATA.rebalances[0]);
      const table = document.createElement('table');
      const thead = document.createElement('thead');
      const headerRow = document.createElement('tr');
      headers.forEach((key) => {{
        const th = document.createElement('th');
        th.textContent = key;
        headerRow.appendChild(th);
      }});
      thead.appendChild(headerRow);
      table.appendChild(thead);
      const tbody = document.createElement('tbody');
      DATA.rebalances.forEach((event) => {{
        const row = document.createElement('tr');
        headers.forEach((key) => {{
          const td = document.createElement('td');
          td.textContent = String(event[key] ?? '');
          row.appendChild(td);
        }});
        tbody.appendChild(row);
      }});
      table.appendChild(tbody);
      tableContainer.appendChild(table);
    }}
  </script>
</body>
</html>
"""


def _format_timestamp(ts_ns: int) -> str:
    return datetime.fromtimestamp(ts_ns / 1_000_000_000).strftime("%Y-%m-%d %H:%M:%S")


def _metrics_table(metrics: Mapping[str, float]) -> str:
    rows = "".join(
        f'<tr><td>{key.replace("_", " ").title()}</td><td class="metric-value">{value:.4f}</td></tr>'
        for key, value in metrics.items()
    )
    return f"<table><tbody>{rows}</tbody></table>"


def _strategy_metrics_table(metrics: Mapping[str, Mapping[str, float]]) -> str:
    rows = []
    for strategy_id, values in metrics.items():
        row = "".join(
            f"<td>{key.replace('_', ' ').title()}: <strong>{value:.4f}</strong></td>"
            for key, value in values.items()
        )
        rows.append(f"<tr><th>{strategy_id}</th>{row}</tr>")
    return f"<table><tbody>{''.join(rows)}</tbody></table>"


def _meta_card(label: str, value: str) -> str:
    return f'<div class="meta-card"><span>{label}</span><strong>{value}</strong></div>'
