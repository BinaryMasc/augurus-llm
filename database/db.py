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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    price REAL,
                    decision TEXT,
                    prompt TEXT,
                    response TEXT
                )
            ''')
            conn.commit()

    def log_decision(self, timestamp: str, price: float, decision: str, prompt: str, response: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO decisions (timestamp, price, decision, prompt, response)
                VALUES (?, ?, ?, ?, ?)
            ''', (timestamp, price, decision, prompt, response))
            conn.commit()

    def log_trade(self, trade_type: str, entry_time: str, entry_price: float, exit_time: str, exit_price: float, size: float, pnl: float, reason: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO trades (type, entry_time, entry_price, exit_time, exit_price, size, pnl, reason)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (trade_type, entry_time, entry_price, exit_time, exit_price, size, pnl, reason))
            conn.commit()

    def get_statistics(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM trades')
            total_trades = cursor.fetchone()[0]
            
            cursor.execute('SELECT SUM(pnl) FROM trades')
            total_pnl = cursor.fetchone()[0] or 0.0
            
            cursor.execute('SELECT COUNT(*) FROM trades WHERE pnl > 0')
            winning_trades = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM trades WHERE pnl <= 0')
            losing_trades = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM decisions')
            total_inferences = cursor.fetchone()[0]

            cursor.execute('SELECT * FROM trades')
            all_trades = cursor.fetchall()
            
            return {
                "total_trades": total_trades,
                "total_pnl": total_pnl,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": (winning_trades / total_trades * 100) if total_trades > 0 else 0,
                "total_inferences": total_inferences,
                "trades": all_trades
            }
