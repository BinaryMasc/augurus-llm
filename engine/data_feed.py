import pandas as pd
from typing import List, Dict

class DataFeed:
    def __init__(self, csv_file: str, timeframe: str = "M1"):
        self.csv_file = csv_file
        self.timeframe = timeframe
        self.df = self._load_data()
        self.current_index = 0
        self.max_index = len(self.df)

    def _load_data(self) -> pd.DataFrame:
        # Load CSV, parse datetime
        df = pd.read_csv(self.csv_file, parse_dates=["datetime"])
        # Some rows might have an extra 'symbol' column, some might not. We take the core columns
        df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
        
        # Set datetime as index for resampling
        df.set_index('datetime', inplace=True)
        
        # If we need to aggregate to a higher timeframe, e.g., M5
        if self.timeframe != "M1":
            # Convert M5 to pandas offset like 5T or 5min
            tf_map = {"M5": "5min", "M15": "15min", "H1": "1h", "H4": "4h", "D1": "1D"}
            pd_tf = tf_map.get(self.timeframe.upper(), "1min")
            
            df = df.resample(pd_tf).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()

        return df.reset_index()

    def get_current_candle(self):
        if self.current_index < self.max_index:
            return self.df.iloc[self.current_index].to_dict()
        return None

    def advance(self, steps: int = 1):
        self.current_index += steps

    def set_index(self, index: int):
        """Sets the cursor to a specific candle index (for resuming sessions)."""
        self.current_index = min(index, self.max_index)

    def get_window(self, candles_to_pass: int) -> List[Dict]:
        """Returns the last `candles_to_pass` up to the current index as a list of dicts."""
        # Ensure we don't go out of bounds backwards
        start_idx = max(0, self.current_index - candles_to_pass + 1)
        end_idx = self.current_index + 1
        window_df = self.df.iloc[start_idx:end_idx]
        
        # Convert datetime to string for JSON serialization
        window_df = window_df.copy()
        window_df['datetime'] = window_df['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        return window_df.to_dict(orient="records")

    def has_next(self) -> bool:
        return self.current_index < self.max_index
