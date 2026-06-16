from flask import Flask, jsonify, render_template_string, request
from database.db import Database

TEMPLATE_INDEX = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Augurus Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; color: #1a1a2e; padding: 24px; }
h1 { font-size: 24px; margin-bottom: 4px; }
.subtitle { color: #6b7280; margin-bottom: 20px; font-size: 14px; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
th { background: #f9fafb; text-align: left; padding: 12px 16px; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; border-bottom: 1px solid #e5e7eb; }
td { padding: 12px 16px; border-bottom: 1px solid #f3f4f6; font-size: 14px; }
tr:hover td { background: #f9fafb; }
a { color: #2563eb; text-decoration: none; font-weight: 500; }
a:hover { text-decoration: underline; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 12px; font-weight: 500; }
.badge-running { background: #dbeafe; color: #1d4ed8; }
.badge-completed { background: #d1fae5; color: #065f46; }
.badge-interrupted { background: #fee2e2; color: #991b1b; }
.pnl-pos { color: #059669; font-weight: 600; }
.pnl-neg { color: #dc2626; font-weight: 600; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
.header-left h1 { margin-bottom: 0; }
</style>
</head>
<body>
<div class="header">
<div class="header-left">
<h1>Augurus Dashboard</h1>
<p class="subtitle">Trading simulation sessions overview</p>
</div>
</div>
<table>
<thead>
<tr>
<th>ID</th><th>Status</th><th>Symbol</th><th>Model</th><th>Reasoning</th><th>First Inference CANDLE</th><th>Last Inference CANDLE</th><th>Timeframe</th>
<th>Trades</th><th>Wins</th><th>Total PnL</th><th>Created</th><th></th>
</tr>
</thead>
<tbody>
{% for s in sessions %}
{% set pnl = s.total_pnl|float %}
<tr>
<td>{{ s.id }}</td>
<td><span class="badge badge-{{ s.status.lower() }}">{{ s.status }}</span></td>
<td>{{ s.symbol }}</td>
<td>{{ s.llm_provider }}/{{ s.model }}</td>
<td>{{ 'True' if s.reasoning else 'False' }}</td>
<td>{{ s.first_candle_date or 'N/A' }}</td>
<td>{{ s.last_candle_inference or 'N/A' }}</td>
<td>{{ s.trading_timeframe }}</td>
<td>{{ s.total_trades }}</td>
<td>{{ s.winning_trades }}</td>
<td class="{{ 'pnl-pos' if pnl >= 0 else 'pnl-neg' }}">{{ '%+.2f'|format(pnl) }}</td>
<td>{{ s.created_at[:10] }}</td>
<td><a href="/session/{{ s.id }}">Details</a></td>
</tr>
{% endfor %}
</tbody>
</table>
</body>
</html>"""

TEMPLATE_SESSION = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Session {{ sid }} - Augurus Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f7fa; color: #1a1a2e; padding: 24px; }
h1 { font-size: 22px; }
.breadcrumb { font-size: 13px; color: #6b7280; margin-bottom: 16px; }
.breadcrumb a { color: #2563eb; text-decoration: none; }
.breadcrumb a:hover { text-decoration: underline; }
.grid { display: grid; gap: 16px; margin-bottom: 20px; }
.grid-6 { grid-template-columns: repeat(6, 1fr); }
.grid-2 { grid-template-columns: repeat(2, 1fr); }
.grid-4 { grid-template-columns: repeat(4, 1fr); }
@media (max-width: 900px) { .grid-6 { grid-template-columns: repeat(3, 1fr); } .grid-4 { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 600px) { .grid-6, .grid-4, .grid-2 { grid-template-columns: 1fr; } }
.card { background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.card-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; margin-bottom: 4px; }
.card-value { font-size: 22px; font-weight: 700; }
.card-sub { font-size: 12px; color: #6b7280; margin-top: 2px; }
.card-chart { min-height: 260px; }
.pnl-pos { color: #059669; }
.pnl-neg { color: #dc2626; }
.info-table { width: 100%; font-size: 13px; }
.info-table td { padding: 4px 8px; }
.info-table td:first-child { color: #6b7280; white-space: nowrap; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 12px; font-weight: 500; }
.badge-running { background: #dbeafe; color: #1d4ed8; }
.badge-completed { background: #d1fae5; color: #065f46; }
.badge-interrupted { background: #fee2e2; color: #991b1b; }
.chart-container { position: relative; height: 240px; }
</style>
</head>
<body>
<div class="breadcrumb"><a href="/">Sessions</a> / Session {{ sid }}</div>
<h1>Session {{ sid }} — {{ stats.session.symbol }} <span class="badge badge-{{ stats.session.status.lower() }}">{{ stats.session.status }}</span></h1>

<div class="grid grid-6" style="margin-top: 16px;">
<div class="card">
<div class="card-label">Total PnL</div>
<div class="card-value {{ 'pnl-pos' if stats.total_pnl >= 0 else 'pnl-neg' }}">{{ '%+.2f'|format(stats.total_pnl) }}</div>
</div>
<div class="card">
<div class="card-label">Win Rate</div>
<div class="card-value">{{ stats.win_rate }}%</div>
<div class="card-sub">{{ stats.winning_trades }}W / {{ stats.losing_trades }}L</div>
</div>
<div class="card">
<div class="card-label">Avg Profit</div>
<div class="card-value pnl-pos">{{ '%+.2f'|format(stats.avg_profit) }}</div>
</div>
<div class="card">
<div class="card-label">Avg Loss</div>
<div class="card-value pnl-neg">{{ '%.2f'|format(stats.avg_loss) }}</div>
</div>
<div class="card">
<div class="card-label">Sharpe Ratio</div>
<div class="card-value">{{ stats.sharpe_ratio }}</div>
</div>
<div class="card">
<div class="card-label">Math Expectation</div>
<div class="card-value">{{ stats.math_expectation }}</div>
</div>
</div>

<div class="grid grid-4">
<div class="card card-chart">
<div class="card-label">Cumulative PnL</div>
<div class="chart-container"><canvas id="chartCumulative"></canvas></div>
</div>
<div class="card card-chart">
<div class="card-label">Long / Short Distribution</div>
<div class="chart-container"><canvas id="chartLongShort"></canvas></div>
</div>
<div class="card card-chart">
<div class="card-label">Win / Loss</div>
<div class="chart-container"><canvas id="chartWinLoss"></canvas></div>
</div>
<div class="card card-chart">
<div class="card-label">PnL per Trade (Strikes)</div>
<div class="chart-container"><canvas id="chartStrikes"></canvas></div>
</div>
</div>

<div class="grid grid-2" style="margin-top: 4px;">
<div class="card">
<div class="card-label">Session Info</div>
<table class="info-table">
<tr><td>Symbol</td><td>{{ stats.session.symbol }}</td></tr>
<tr><td>Model</td><td>{{ stats.session.llm_provider }}/{{ stats.session.model }}</td></tr>
<tr><td>Reasoning</td><td>{{ 'Enabled' if stats.session.reasoning else 'Disabled' }}</td></tr>
<tr><td>First Candle Inference</td><td>{{ stats.first_candle_date }}</td></tr>
<tr><td>Last Candle Inference</td><td>{{ stats.last_candle_inference }}</td></tr>
<tr><td>Timeframe</td><td>{{ stats.session.trading_timeframe }}</td></tr>
<tr><td>CSV File</td><td style="font-size:11px;word-break:break-all;">{{ stats.session.csv_file }}</td></tr>
<tr><td>Created</td><td>{{ stats.session.created_at }}</td></tr>
<tr><td>Status</td><td>{{ stats.session.status }}</td></tr>
<tr><td>Contract Size</td><td>{{ stats.session.contract_size }}</td></tr>
<tr><td>SL / TP</td><td>{{ stats.session.stop_loss_percentage }}% / {{ stats.session.take_profit_percentage }}%</td></tr>
<tr><td>Max Duration</td><td>{{ stats.session.max_trade_duration_m1 }} candles</td></tr>
<tr><td>Inference Freq</td><td>Every {{ stats.session.inference_frequency_m1 }} candles</td></tr>
<tr><td>Candles to Pass</td><td>{{ stats.session.candles_to_pass }}</td></tr>
</table>
</div>
<div class="card">
<div class="card-label">Long / Short Breakdown</div>
<table class="info-table">
<tr><td>Long Trades</td><td>{{ stats.long_count }} (PnL: {{ '%+.2f'|format(stats.long_pnl) }})</td></tr>
<tr><td>Short Trades</td><td>{{ stats.short_count }} (PnL: {{ '%+.2f'|format(stats.short_pnl) }})</td></tr>
</table>
<div class="card-label" style="margin-top: 16px;">All Trades ({{ stats.total_trades }})</div>
<div style="max-height: 300px; overflow-y: auto; margin-top: 8px;">
<table class="info-table" style="width:100%;">
<thead>
<tr style="border-bottom:1px solid #e5e7eb;"><td style="font-weight:600;">#</td><td style="font-weight:600;">Type</td><td style="font-weight:600;">Entry</td><td style="font-weight:600;">Exit</td><td style="font-weight:600;">PnL</td><td style="font-weight:600;">Reason</td></tr>
</thead>
<tbody>
{% for t in stats.trades %}
<tr>
<td>{{ loop.index }}</td>
<td>{{ 'Long' if t.type == 'BUY' else 'Short' }}</td>
<td>{{ t.entry_price }}</td>
<td>{{ t.exit_price }}</td>
<td class="{{ 'pnl-pos' if (t.pnl or 0) >= 0 else 'pnl-neg' }}">{{ '%+.2f'|format(t.pnl or 0) }}</td>
<td>{{ t.reason }}</td>
</tr>
{% endfor %}
</tbody>
</table>
</div>
</div>
</div>

<script>
const cumData = {{ stats.cumulative_pnl | tojson }};
const pnlData = {{ stats.pnl_array | tojson }};

new Chart(document.getElementById('chartCumulative'), {
type: 'line',
data: {
labels: cumData.map(d => '#'.concat(d.index)),
datasets: [{
label: 'Cumulative PnL',
data: cumData.map(d => d.pnl),
borderColor: '#2563eb',
backgroundColor: 'rgba(37,99,235,0.08)',
fill: true,
tension: 0.3,
pointRadius: 2,
}]
},
options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 10 } },
y: { grid: { color: '#f3f4f6' } } } }
});

new Chart(document.getElementById('chartLongShort'), {
type: 'doughnut',
data: {
labels: ['Long (BUY)', 'Short (SELL)'],
datasets: [{
data: [{{ stats.long_count }}, {{ stats.short_count }}],
backgroundColor: ['#059669', '#2563eb'],
}]
},
options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
});

const winLossTotal = {{ stats.winning_trades }} + {{ stats.losing_trades }};
new Chart(document.getElementById('chartWinLoss'), {
type: 'doughnut',
data: {
labels: ['Wins', 'Losses'],
datasets: [{
data: [{{ stats.winning_trades }}, {{ stats.losing_trades }}],
backgroundColor: ['#059669', '#dc2626'],
}]
},
options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } } }
});

new Chart(document.getElementById('chartStrikes'), {
type: 'bar',
data: {
labels: pnlData.map(d => '#'.concat(d.index)),
datasets: [{
label: 'PnL',
data: pnlData.map(d => d.pnl),
backgroundColor: pnlData.map(d => d.pnl >= 0 ? '#059669' : '#dc2626'),
borderRadius: 2,
}]
},
options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } },
scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 20 } },
y: { grid: { color: '#f3f4f6' } } } }
});
</script>
</body>
</html>"""


def create_app(db: Database):
    app = Flask(__name__)

    @app.route('/')
    def index():
        sessions = db.get_sessions_list()
        return render_template_string(TEMPLATE_INDEX, sessions=sessions)

    @app.route('/session/<int:session_id>')
    def session_detail(session_id):
        stats = db.get_session_details(session_id)
        if stats is None:
            return "Session not found", 404
        return render_template_string(TEMPLATE_SESSION, sid=session_id, stats=stats)

    @app.route('/api/sessions')
    def api_sessions():
        sessions = db.get_sessions_list()
        return jsonify(sessions)

    @app.route('/api/session/<int:session_id>/stats')
    def api_session_stats(session_id):
        stats = db.get_session_details(session_id)
        if stats is None:
            return jsonify({'error': 'Session not found'}), 404
        return jsonify(stats)

    return app


def run_dashboard(db_path: str, host: str = '0.0.0.0', port: int = 8080):
    db = Database(db_path)
    app = create_app(db)
    print(f"[*] Augurus Dashboard starting on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
