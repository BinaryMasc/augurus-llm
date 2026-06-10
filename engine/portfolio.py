from typing import Optional, Dict
from database.db import Database

class Portfolio:
    def __init__(self, db: Database, config: dict):
        self.db = db
        self.config = config
        
        self.active_trade: Optional[Dict] = None
        
        self.contract_size = config.get("contract_size", 1.0)
        self.sl_pct = config.get("stop_loss_percentage", 5.0) / 100.0
        self.tp_pct = config.get("take_profit_percentage", 10.0) / 100.0
        self.max_duration_m1 = config.get("max_trade_duration_m1", 60)

    def get_state(self, current_price: float) -> Dict:
        """Returns current state to feed into LLM."""
        if not self.active_trade:
            return {"status": "NO_ACTIVE_TRADE"}
        
        # Calculate unrealized PnL
        entry = self.active_trade['entry_price']
        size = self.active_trade['size']
        if self.active_trade['type'] == 'BUY':
            pnl = (current_price - entry) * size
            pnl_pct = (current_price - entry) / entry
        else: # SELL
            pnl = (entry - current_price) * size
            pnl_pct = (entry - current_price) / entry

        return {
            "status": "ACTIVE_TRADE",
            "type": self.active_trade['type'],
            "entry_price": entry,
            "current_price": current_price,
            "unrealized_pnl": round(pnl, 2),
            "unrealized_pnl_pct": round(pnl_pct * 100, 2),
            "duration_candles": self.active_trade['duration_candles']
        }

    def update(self, current_time: str, current_price: float):
        """Called every candle to update duration and check SL/TP."""
        if not self.active_trade:
            return

        self.active_trade['duration_candles'] += 1
        
        state = self.get_state(current_price)
        pnl_pct = state['unrealized_pnl_pct'] / 100.0

        # Check Stop Loss
        if pnl_pct <= -self.sl_pct:
            self.close_trade(current_time, current_price, reason="STOP_LOSS")
            return

        # Check Take Profit
        if pnl_pct >= self.tp_pct:
            self.close_trade(current_time, current_price, reason="TAKE_PROFIT")
            return

        # Check Max Duration
        if self.active_trade['duration_candles'] >= self.max_duration_m1:
            self.close_trade(current_time, current_price, reason="MAX_DURATION_EXCEEDED")

    def execute_decision(self, decision: str, current_time: str, current_price: float):
        """Process LLM decision."""
        if decision == "WAIT":
            return
            
        elif decision == "CLOSE":
            if self.active_trade:
                self.close_trade(current_time, current_price, reason="LLM_DECISION")
                
        elif decision in ["BUY", "SELL"]:
            if self.active_trade:
                # If we are already in the same direction, ignore
                if self.active_trade['type'] == decision:
                    return
                # If opposite direction, close current and open new (reverse)
                self.close_trade(current_time, current_price, reason="REVERSE_POSITION")
            
            # Open new trade
            self.active_trade = {
                "type": decision,
                "entry_time": current_time,
                "entry_price": current_price,
                "size": self.contract_size,
                "duration_candles": 0
            }

    def close_trade(self, current_time: str, current_price: float, reason: str):
        if not self.active_trade:
            return
            
        entry = self.active_trade['entry_price']
        size = self.active_trade['size']
        trade_type = self.active_trade['type']
        
        if trade_type == 'BUY':
            pnl = (current_price - entry) * size
        else: # SELL
            pnl = (entry - current_price) * size

        self.db.log_trade(
            trade_type=trade_type,
            entry_time=self.active_trade['entry_time'],
            entry_price=entry,
            exit_time=current_time,
            exit_price=current_price,
            size=size,
            pnl=pnl,
            reason=reason
        )
        
        self.active_trade = None
