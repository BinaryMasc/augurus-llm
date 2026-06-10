# Codebase Resume — Augurus LLM Trading Simulator

> **Purpose**: Quick-reference document for AI agents working on this codebase.
> Last updated: 2026-06-10

---

## 1. Project Overview

Augurus is a **CLI-based backtesting simulator** that replays historical candlestick data through an LLM to generate trading decisions (BUY / SELL / CLOSE / WAIT). Trades are tracked with a portfolio manager that enforces risk rules (SL, TP, max duration), and all decisions and trades are persisted to a local SQLite database.

**Tech stack**: Python 3 · Pandas · PyYAML · Requests · python-dotenv · google-generativeai  
**LLM backends**: Google Gemini (cloud) **or** Ollama (local). Selected via `config.yaml → llm`.

---

## 2. Directory Structure

```
augurus-llm/
├── main.py                  # Entry point – simulation loop & CLI
├── config.yaml              # All tuneable parameters
├── .env                     # API keys (GEMINI_API_KEY or GOOGLE_API_KEY)
├── requirements.txt         # Python dependencies
├── trading_sim.sqlite       # SQLite database (runtime-generated)
├── database/
│   └── db.py                # Database class – schema init, logging, stats
├── engine/
│   ├── data_feed.py         # DataFeed – CSV loading & timeframe aggregation
│   ├── llm_client.py        # LLMClient – prompt construction & LLM calls
│   └── portfolio.py         # Portfolio – trade execution, SL/TP, PnL
└── venv/                    # Virtual environment (gitignored)
```

---

## 3. Data Flow

```
CSV file ──► DataFeed ──► candle window ──► LLMClient (prompt + portfolio state)
                                                │
                                          LLM response
                                                │
                                          parsed decision
                                           (BUY/SELL/CLOSE/WAIT)
                                                │
                              ┌─────────────────┼─────────────────┐
                              ▼                                   ▼
                     Portfolio.execute_decision()         Database.log_decision()
                      (open/close/reverse trade)          (persist prompt+response)
                              │
                    Portfolio.close_trade()
                              │
                     Database.log_trade()
```

### Simulation Loop (`main.py → run_simulation`)

1. Load config, init `Database`, `DataFeed`, `Portfolio`, `LLMClient`.
2. Iterate candle-by-candle via `DataFeed`:
   - `portfolio.update()` — check SL/TP/max-duration on every candle.
   - At every `inference_frequency_m1` candles (after the initial `candles_to_pass` warm-up): build a price window, get portfolio state, call the LLM, execute the decision.
3. On completion (or Ctrl+C), force-close any open trade with reason `END_OF_SIMULATION`.
4. Print elapsed time and statistics.

---

## 4. Module Details

### `main.py`

| Function | Description |
|---|---|
| `load_config()` | Reads `config.yaml`, returns dict. |
| `run_simulation(debug)` | Main loop. `--debug` prints full prompts/responses per inference. |
| `print_statistics(db)` | Queries DB, prints win rate / PnL / last 5 trades. Standalone via `--statistics`. |

**CLI flags**: `--statistics` (print stats and exit), `--debug` (verbose inference logging).

---

### `database/db.py` — class `Database`

Wraps SQLite with context-managed connections (new connection per call).

| Method | Description |
|---|---|
| `_init_db()` | Creates `trades` and `decisions` tables if not exists. |
| `log_decision(timestamp, price, decision, prompt, response)` | Inserts into `decisions`. |
| `log_trade(trade_type, entry_time, entry_price, exit_time, exit_price, size, pnl, reason)` | Inserts into `trades`. |
| `get_statistics()` | Returns dict with `total_trades`, `total_pnl`, `winning_trades`, `losing_trades`, `win_rate`, `total_inferences`, `trades` (list of all trade tuples). |

#### SQLite Schema

```sql
CREATE TABLE trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    type        TEXT,        -- "BUY" or "SELL"
    entry_time  TEXT,        -- ISO timestamp string
    entry_price REAL,
    exit_time   TEXT,
    exit_price  REAL,
    size        REAL,        -- contract size (always config value)
    pnl         REAL,        -- realized PnL in price units
    reason      TEXT         -- "STOP_LOSS" | "TAKE_PROFIT" | "MAX_DURATION_EXCEEDED"
                             -- | "LLM_DECISION" | "REVERSE_POSITION" | "END_OF_SIMULATION"
);

CREATE TABLE decisions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    price     REAL,
    decision  TEXT,          -- "BUY" | "SELL" | "CLOSE" | "WAIT"
    prompt    TEXT,          -- full prompt sent to LLM
    response  TEXT           -- raw LLM response text
);
```

---

### `engine/data_feed.py` — class `DataFeed`

| Method | Description |
|---|---|
| `__init__(csv_file, timeframe)` | Loads CSV, aggregates to target timeframe. |
| `_load_data()` | Pandas resample; expects columns `datetime, open, high, low, close, volume`. |
| `get_current_candle()` | Returns current row as dict, or `None`. |
| `advance(steps)` | Moves the cursor forward. |
| `get_window(candles_to_pass)` | Returns last N candles as `List[Dict]` (datetimes stringified). |
| `has_next()` | Bounds check. |

**Supported timeframes** (via `tf_map`): `M1` (raw), `M5`, `M15`, `H1`, `H4`, `D1`.

**Expected CSV columns**: `datetime`, `open`, `high`, `low`, `close`, `volume`.

---

### `engine/llm_client.py` — class `LLMClient`

| Method | Description |
|---|---|
| `__init__(config)` | Picks provider from `config["llm"]`. Inits Gemini SDK or Ollama endpoint. |
| `generate_decision(window, portfolio_state)` | Builds prompt, calls LLM, returns `(decision, prompt, raw_response)`. |
| `_parse_decision(raw_text)` | Extracts first valid keyword (`BUY > SELL > CLOSE > WAIT` priority). |

**Prompt structure**: system prompt (role + risk + output format) + JSON of `portfolio_state` and `recent_candles` + `DECISION:` suffix.

**Provider details**:

| Provider | Endpoint | Retry logic |
|---|---|---|
| `gemini` | `google.generativeai` SDK | Up to 5 retries on 429/Quota errors, 35s backoff |
| `ollama` | `POST {url}/api/generate` | No retries; returns WAIT on error |

Both use `temperature=0.1` and `max_output_tokens=10` to force terse output.

**API key resolution** (Gemini): checks `GEMINI_API_KEY` → `GOOGLE_API_KEY` from env. Strips all whitespace to avoid gRPC metadata errors.

---

### `engine/portfolio.py` — class `Portfolio`

| Method | Description |
|---|---|
| `__init__(db, config)` | Stores config: `contract_size`, `sl_pct`, `tp_pct`, `max_duration_m1`. |
| `get_state(current_price)` | Returns dict for LLM context: either `{status: "NO_ACTIVE_TRADE"}` or full trade details with unrealized PnL. |
| `update(current_time, current_price)` | Called every candle. Increments duration, checks SL/TP/max-duration → auto-closes. |
| `execute_decision(decision, current_time, current_price)` | Processes LLM output: WAIT=noop, CLOSE=close, BUY/SELL=open (or reverse if opposite). |
| `close_trade(current_time, current_price, reason)` | Calculates PnL, logs to DB, clears `active_trade`. |

**Key rules**:
- Only **one active trade** at a time.
- Same-direction signal while in a trade → ignored.
- Opposite-direction signal → closes current trade (reason `REVERSE_POSITION`), then opens new.
- PnL: `(exit - entry) * size` for BUY, `(entry - exit) * size` for SELL.

---

## 5. Configuration Reference (`config.yaml`)

```yaml
simulation:
  csv_file: "../OpenBackTest/public/data/btc_usdt_m1_jan2025-apr2026.csv"
  candles_to_pass: 15          # Price window size sent to LLM
  trading_timeframe: "M5"      # Aggregation level (M1, M5, M15, H1, H4, D1)
  max_trade_duration_m1: 120   # Auto-close after N candles
  inference_frequency_m1: 10   # Run LLM every N candles
  contract_size: 1.0           # Fixed lot size
  max_risk_per_trade_percentage: 2.0  # Passed to LLM prompt
  stop_loss_percentage: 5.0    # Global SL (%)
  take_profit_percentage: 5.0  # Global TP (%)
  db_path: "trading_sim.sqlite"

llm: "gemini"                  # "gemini" or "ollama"

ollama:
  url: "http://localhost:11434"
  model: "gemma4-12b-Q8"

gemini:
  model: "gemini-3.1-flash-lite"
```

---

## 6. Environment Variables (`.env`)

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | If `llm: gemini` | Google AI Studio API key |
| `GOOGLE_API_KEY` | Fallback | Alternative env var name for the same key |

Loaded via `python-dotenv` from the script's directory at startup.

---

## 7. Running the Project

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run simulation
python main.py                    # Normal run
python main.py --debug            # Verbose (shows prompts/responses)
python main.py --statistics       # Print stats from DB only

# Prerequisites
# - CSV data file at the path specified in config.yaml
# - For Gemini: valid API key in .env
# - For Ollama: local Ollama server running with the configured model
```

---

## 8. Conventions & Patterns

- **No tests** exist yet. No CI/CD.
- **No package init files** (`__init__.py`) — modules are imported by directory path directly.
- **Timestamps** are stored and passed as ISO-format strings (`YYYY-MM-DD HH:MM:SS`).
- **Error handling** in `LLMClient` defaults to `WAIT` — the simulation never crashes on a failed LLM call.
- **Database connections** are opened and closed per operation (no connection pooling).
- **Comments** are written in English.
- **Trade close reasons** are a fixed set of string constants (not an enum): `STOP_LOSS`, `TAKE_PROFIT`, `MAX_DURATION_EXCEEDED`, `LLM_DECISION`, `REVERSE_POSITION`, `END_OF_SIMULATION`.
