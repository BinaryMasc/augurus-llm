import argparse
import yaml
import time
import re
import os
from dotenv import load_dotenv
from database.db import Database
from engine.data_feed import DataFeed
from engine.portfolio import Portfolio
from engine.llm_client import LLMClient

def load_config(config_path="config.yaml"):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def extract_symbol(csv_path: str) -> str:
    """Derives symbol from CSV filename. E.g. 'btc_usdt_m1_jan2025.csv' -> 'BTCUSDT'."""
    basename = os.path.basename(csv_path).lower()
    # Remove file extension
    name = os.path.splitext(basename)[0]
    # Match the symbol part before the timeframe indicator (_m1_, _m5_, _h1_, etc.)
    match = re.match(r'^(.+?)_(?:m\d+|h\d+|d\d+)_', name)
    if match:
        symbol = match.group(1).replace('_', '').upper()
    else:
        # Fallback: use the whole name without underscores
        symbol = name.replace('_', '').upper()
    return symbol

def run_simulation(debug=False, continue_last=False):
    config = load_config()
    sim_config = config['simulation']
    db = Database(sim_config['db_path'])

    if continue_last is not False:
        if isinstance(continue_last, int):
            session = db.get_session_by_id(continue_last)
            if session is None:
                print(f"[!] Session {continue_last} not found. Starting a new simulation instead.")
                continue_last = False
            elif session['status'] == 'COMPLETED':
                print(f"[!] Session {session['id']} is already COMPLETED. Starting a new simulation.")
                continue_last = False
            else:
                print(f"Resuming session {session['id']} (created {session['created_at']}, status: {session['status']})")
        else:
            # Resume the last session using its stored parameters
            session = db.get_last_session()
            if session is None:
                print("[!] No previous session found. Starting a new simulation instead.")
                continue_last = False
            elif session['status'] == 'COMPLETED':
                print(f"[!] Last session (ID {session['id']}) is already COMPLETED. Starting a new simulation.")
                continue_last = False
            else:
                print(f"Resuming session {session['id']} (created {session['created_at']}, status: {session['status']})")

    if continue_last:
        # Use stored session parameters
        session_id = session['id']
        csv_file = session['csv_file']
        trading_timeframe = session['trading_timeframe']
        candles_to_pass = session['candles_to_pass']
        inference_freq = session['inference_frequency_m1']
        model_name = session['model']
        llm_provider = session['llm_provider']
        resume_index = session['last_candle_index']

        # Build a config-like dict for Portfolio from session parameters
        portfolio_config = {
            'contract_size': session['contract_size'],
            'stop_loss_percentage': session['stop_loss_percentage'],
            'take_profit_percentage': session['take_profit_percentage'],
            'max_trade_duration_m1': session['max_trade_duration_m1'],
        }

        # Query session stats for display
        stats = db.get_statistics(session_id=session_id)
        last_ts = session.get('last_candle_timestamp', 'N/A')

        print(f"  CSV: {csv_file}")
        print(f"  Model: {llm_provider}/{model_name}")
        print(f"  Timeframe: {trading_timeframe} | Candles to pass: {candles_to_pass} | Inference freq: {inference_freq}")
        print(f"  Last checkpoint: candle {resume_index} @ {last_ts}")
        print(f"  Inferences so far: {stats['total_inferences']} | Trades so far: {stats['total_trades']}")

        data_feed = DataFeed(csv_file, trading_timeframe)
        data_feed.set_index(resume_index)
        portfolio = Portfolio(db, portfolio_config, session_id=session_id)
        llm = LLMClient(config)

        # Update session status back to RUNNING
        db.update_session_status(session_id, 'RUNNING')
    else:
        # New session
        csv_file = sim_config['csv_file']
        trading_timeframe = sim_config['trading_timeframe']
        candles_to_pass = sim_config['candles_to_pass']
        inference_freq = sim_config['inference_frequency_m1']

        print(f"Initializing simulation with CSV: {csv_file}")
        data_feed = DataFeed(csv_file, trading_timeframe)
        llm = LLMClient(config)

        symbol = extract_symbol(csv_file)
        model_name = llm.model_name
        llm_provider = llm.provider

        session_id = db.create_session({
            'csv_file': csv_file,
            'symbol': symbol,
            'model': model_name,
            'llm_provider': llm_provider,
            'trading_timeframe': trading_timeframe,
            'inference_frequency_m1': inference_freq,
            'candles_to_pass': candles_to_pass,
            'max_trade_duration_m1': sim_config.get('max_trade_duration_m1', 60),
            'contract_size': sim_config.get('contract_size', 1.0),
            'stop_loss_percentage': sim_config.get('stop_loss_percentage', 5.0),
            'take_profit_percentage': sim_config.get('take_profit_percentage', 5.0),
        })
        print(f"Created session {session_id} (symbol: {symbol}, model: {llm_provider}/{model_name})")

        portfolio = Portfolio(db, sim_config, session_id=session_id)

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
                
                db.log_decision(current_time, current_price, decision, prompt, response,
                                session_id=session_id, model=model_name)
                portfolio.execute_decision(decision, current_time, current_price)
                
                inferences_made += 1
                
                # Update session progress checkpoint
                db.update_session_progress(session_id, idx, current_time)

            data_feed.advance(1)
    except KeyboardInterrupt:
        print("\n[!] Simulation interrupted by user (CTRL+C). Cleaning up and saving state...")
        db.update_session_status(session_id, 'INTERRUPTED')

    # Close any open trade at the end of the simulation
    if portfolio.active_trade:
        last_candle = data_feed.df.iloc[-1]
        t = last_candle['datetime']
        t_str = t.strftime('%Y-%m-%d %H:%M:%S') if not isinstance(t, str) else t
        portfolio.close_trade(t_str, last_candle['close'], reason="END_OF_SIMULATION")

    elapsed = time.time() - start_time
    
    # Mark session as completed (only if not already interrupted)
    try:
        session_row = db.get_last_session()
        if session_row and session_row['id'] == session_id and session_row['status'] != 'INTERRUPTED':
            db.update_session_status(session_id, 'COMPLETED')
    except Exception:
        pass

    print(f"Simulation finished in {elapsed:.2f} seconds.")
    print(f"Total inferences made: {inferences_made}")
    print_statistics(db, session_id=session_id)


def print_statistics(db=None, session_id=None):
    if db is None:
        config = load_config()
        db = Database(config['simulation']['db_path'])
        
    stats = db.get_statistics(session_id=session_id)

    scope_label = f" (Session {session_id})" if session_id else " (All Sessions)"
    print(f"\n{'='*30}")
    print(f"  SIMULATION STATISTICS{scope_label}")
    print("="*30)
    print(f"Total Trades:     {stats['total_trades']}")
    print(f"Winning Trades:   {stats['winning_trades']}")
    print(f"Losing Trades:    {stats['losing_trades']}")
    print(f"Win Rate:         {stats['win_rate']:.2f}%")
    print(f"Total PnL:        {stats['total_pnl']:.2f}")
    print(f"Total Inferences: {stats['total_inferences']}")
    print("="*30)
    
    if stats['total_trades'] > 0:
        print("\nLast 5 Trades:")
        for t in stats['trades'][-5:]:
            pnl_val = float(t['pnl']) if t.get('pnl') is not None else 0.0
            pnl_str = f"+{pnl_val:.2f}" if pnl_val > 0 else f"{pnl_val:.2f}"
            print(f"[{t['entry_time']}] {t['type']} @ {t['entry_price']:.2f} -> Closed @ {t['exit_price']:.2f} [{t['reason']}] | PnL: {pnl_str}")

if __name__ == "__main__":
    # Ensure .env is loaded from the script directory
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    load_dotenv(env_path)
    
    parser = argparse.ArgumentParser(description="LLM Trading Simulator CLI")
    parser.add_argument("--statistics", action="store_true", help="Print statistics from the database and exit")
    parser.add_argument("--debug", action="store_true", help="Print prompts and raw responses for each inference")
    parser.add_argument("--continue", dest="continue_last", nargs="?", const=True, type=int,
                        help="Continue the last simulation session, or a specific session by ID (e.g. --continue 1)")
    
    args = parser.parse_args()
    
    if args.statistics:
        print_statistics()
    else:
        run_simulation(debug=args.debug, continue_last=args.continue_last)
