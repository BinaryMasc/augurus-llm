import sqlite3
from typing import Dict, List, Optional
from datetime import datetime

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Sessions table (new)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT,
                    status TEXT DEFAULT 'RUNNING',
                    csv_file TEXT,
                    symbol TEXT,
                    model TEXT,
                    llm_provider TEXT,
                    trading_timeframe TEXT,
                    inference_frequency_m1 INTEGER,
                    candles_to_pass INTEGER,
                    max_trade_duration_m1 INTEGER,
                    contract_size REAL,
                    stop_loss_percentage REAL,
                    take_profit_percentage REAL,
                    last_candle_index INTEGER DEFAULT 0,
                    last_candle_timestamp TEXT
                )
            ''')
            # Trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    type TEXT,
                    entry_time TEXT,
                    entry_price REAL,
                    exit_time TEXT,
                    exit_price REAL,
                    size REAL,
                    pnl REAL,
                    reason TEXT
                )
            ''')
            # Decisions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    model TEXT,
                    timestamp TEXT,
                    price REAL,
                    decision TEXT,
                    prompt TEXT,
                    response TEXT
                )
            ''')
            conn.commit()

            # Backward compatibility: add new columns to existing tables
            # self._migrate_add_column(cursor, 'trades', 'session_id', 'INTEGER')
            # self._migrate_add_column(cursor, 'decisions', 'session_id', 'INTEGER')
            # self._migrate_add_column(cursor, 'decisions', 'model', 'TEXT')
            conn.commit()

    def _migrate_add_column(self, cursor, table: str, column: str, col_type: str):
        """Safely adds a column to an existing table. No-op if it already exists."""
        try:
            cursor.execute(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}')
        except sqlite3.OperationalError:
            # Column already exists
            pass

    # ── Session management ──────────────────────────────────────────────

    def create_session(self, params: Dict) -> int:
        """Creates a new session row and returns its ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sessions (
                    created_at, status, csv_file, symbol, model, llm_provider,
                    trading_timeframe, inference_frequency_m1, candles_to_pass,
                    max_trade_duration_m1, contract_size,
                    stop_loss_percentage, take_profit_percentage
                ) VALUES (?, 'RUNNING', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                params['csv_file'],
                params['symbol'],
                params['model'],
                params['llm_provider'],
                params['trading_timeframe'],
                params['inference_frequency_m1'],
                params['candles_to_pass'],
                params['max_trade_duration_m1'],
                params['contract_size'],
                params['stop_loss_percentage'],
                params['take_profit_percentage'],
            ))
            conn.commit()
            return cursor.lastrowid

    def get_last_session(self) -> Optional[Dict]:
        """Returns the most recent session as a dict, or None."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions ORDER BY id DESC LIMIT 1')
            row = cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    def get_session_by_id(self, session_id: int) -> Optional[Dict]:
        """Returns a session by its ID, or None."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return dict(row)

    def update_session_progress(self, session_id: int, candle_index: int, candle_timestamp: str):
        """Updates the resume checkpoint for a session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE sessions SET last_candle_index = ?, last_candle_timestamp = ?
                WHERE id = ?
            ''', (candle_index, candle_timestamp, session_id))
            conn.commit()

    def update_session_status(self, session_id: int, status: str):
        """Sets session status (COMPLETED, INTERRUPTED)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE sessions SET status = ? WHERE id = ?', (status, session_id))
            conn.commit()

    # ── Logging ─────────────────────────────────────────────────────────

    def log_decision(self, timestamp: str, price: float, decision: str, prompt: str, response: str,
                     session_id: int = None, model: str = None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO decisions (session_id, model, timestamp, price, decision, prompt, response)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (session_id, model, timestamp, price, decision, prompt, response))
            conn.commit()

    def log_trade(self, trade_type: str, entry_time: str, entry_price: float, exit_time: str, exit_price: float,
                  size: float, pnl: float, reason: str, session_id: int = None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trades (session_id, type, entry_time, entry_price, exit_time, exit_price, size, pnl, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session_id, trade_type, entry_time, entry_price, exit_time, exit_price, size, pnl, reason))
            conn.commit()

    # ── Statistics ──────────────────────────────────────────────────────

    def get_statistics(self, session_id: int = None) -> Dict:
        """Returns stats. If session_id is given, scopes to that session only."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            if session_id is not None:
                session_filter = ' WHERE session_id = ?'
                win_filter = ' WHERE session_id = ? AND pnl > 0'
                lose_filter = ' WHERE session_id = ? AND pnl <= 0'
                params = (session_id,)
            else:
                session_filter = ''
                win_filter = ' WHERE pnl > 0'
                lose_filter = ' WHERE pnl <= 0'
                params = ()

            cursor.execute(f'SELECT COUNT(*) FROM trades{session_filter}', params)
            total_trades = cursor.fetchone()[0]
            
            cursor.execute(f'SELECT SUM(pnl) FROM trades{session_filter}', params)
            total_pnl = cursor.fetchone()[0] or 0.0
            
            cursor.execute(f'SELECT COUNT(*) FROM trades{win_filter}', params)
            winning_trades = cursor.fetchone()[0]
            
            cursor.execute(f'SELECT COUNT(*) FROM trades{lose_filter}', params)
            losing_trades = cursor.fetchone()[0]

            cursor.execute(f'SELECT COUNT(*) FROM decisions{session_filter}', params)
            total_inferences = cursor.fetchone()[0]

            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f'SELECT * FROM trades{session_filter}', params)
            all_trades = [dict(row) for row in cursor.fetchall()]
            
            return {
                "total_trades": total_trades,
                "total_pnl": total_pnl,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": (winning_trades / total_trades * 100) if total_trades > 0 else 0,
                "total_inferences": total_inferences,
                "trades": all_trades
            }
