import argparse
import yaml
import time
import os
from dotenv import load_dotenv
from database.db import Database
from engine.data_feed import DataFeed
from engine.portfolio import Portfolio
from engine.llm_client import LLMClient

def load_config(config_path="config.yaml"):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def run_simulation(debug=False):
    config = load_config()
    sim_config = config['simulation']
    
    print(f"Initializing simulation with CSV: {sim_config['csv_file']}")
    db = Database(sim_config['db_path'])
    data_feed = DataFeed(sim_config['csv_file'], sim_config['trading_timeframe'])
    portfolio = Portfolio(db, sim_config)
    llm = LLMClient(config)

    candles_to_pass = sim_config['candles_to_pass']
    inference_freq = sim_config['inference_frequency_m1']

    print("Starting simulation loop...")
    start_time = time.time()
    
    inferences_made = 0
    
    try:
        while data_feed.has_next():
            candle = data_feed.get_current_candle()
            current_time = candle['datetime']
            if not isinstance(current_time, str):
                current_time = current_time.strftime('%Y-%m-%d %H:%M:%S')
            
            current_price = candle['close']
            
            # Update portfolio state (checks SL/TP and max duration)
            portfolio.update(current_time, current_price)
            
            idx = data_feed.current_index
            if idx >= candles_to_pass and idx % inference_freq == 0:
                window = data_feed.get_window(candles_to_pass)
                state = portfolio.get_state(current_price)
                
                # Print minimal progress
                if inferences_made % 10 == 0:
                    print(f"[{current_time}] Price: {current_price:.2f} | Inferences: {inferences_made} | Active Trade: {state['status']}")
                
                decision, prompt, response = llm.generate_decision(window, state)
                
                if debug:
                    print(f"\n{'='*20} DEBUG INFERENCE {'='*20}")
                    print(f"PROMPT:\n{prompt}\n")
                    print(f"RAW RESPONSE:\n{response}\n")
                    print(f"PARSED DECISION: {decision}")
                    print(f"{'='*57}\n")
                
                db.log_decision(current_time, current_price, decision, prompt, response)
                portfolio.execute_decision(decision, current_time, current_price)
                
                inferences_made += 1

            data_feed.advance(1)
    except KeyboardInterrupt:
        print("\n[!] Simulation interrupted by user (CTRL+C). Cleaning up and saving state...")

    # Close any open trade at the end of the simulation
    if portfolio.active_trade:
        last_candle = data_feed.df.iloc[-1]
        t = last_candle['datetime']
        t_str = t.strftime('%Y-%m-%d %H:%M:%S') if not isinstance(t, str) else t
        portfolio.close_trade(t_str, last_candle['close'], reason="END_OF_SIMULATION")

    elapsed = time.time() - start_time
    print(f"Simulation finished in {elapsed:.2f} seconds.")
    print(f"Total inferences made: {inferences_made}")
    print_statistics(db)


def print_statistics(db=None):
    if db is None:
        config = load_config()
        db = Database(config['simulation']['db_path'])
        
    stats = db.get_statistics()
    print("\n" + "="*30)
    print("      SIMULATION STATISTICS")
    print("="*30)
    print(f"Total Trades:   {stats['total_trades']}")
    print(f"Winning Trades: {stats['winning_trades']}")
    print(f"Losing Trades:  {stats['losing_trades']}")
    print(f"Win Rate:       {stats['win_rate']:.2f}%")
    print(f"Total PnL:      {stats['total_pnl']:.2f}")
    print("="*30)
    
    if stats['total_trades'] > 0:
        print("\nLast 5 Trades:")
        for t in stats['trades'][-5:]:
            # t is a tuple: (id, type, entry_time, entry_price, exit_time, exit_price, size, pnl, reason)
            pnl_str = f"+{t[7]:.2f}" if t[7] > 0 else f"{t[7]:.2f}"
            print(f"[{t[2]}] {t[1]} @ {t[3]:.2f} -> Closed @ {t[5]:.2f} [{t[8]}] | PnL: {pnl_str}")

if __name__ == "__main__":
    # Ensure .env is loaded from the script directory
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    load_dotenv(env_path)
    
    parser = argparse.ArgumentParser(description="LLM Trading Simulator CLI")
    parser.add_argument("--statistics", action="store_true", help="Print statistics from the database and exit")
    parser.add_argument("--debug", action="store_true", help="Print prompts and raw responses for each inference")
    
    args = parser.parse_args()
    
    if args.statistics:
        print_statistics()
    else:
        run_simulation(debug=args.debug)
