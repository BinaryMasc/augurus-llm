# Augurus LLM Trading Simulator

A CLI tool that simulates trading by parsing CSV candlestick data and using an Ollama or Gemini LLM to make trading decisions in real-time.

## Features (Current)
- Parses historical CSV data (e.g., M1 data) and aggregates to custom timeframes (e.g., M5).
- Connects to Ollama or Gemini for trading decisions.
- Prompts are token-optimized: requires minimal structured output from the LLM.
- Calculates PnL, handles fixed contract sizes, and enforces global SL/TP and maximum trade durations.
- SQLite database for storing trades and statistics.
- `--statistics` flag to view PnL and trade history.

## Futurables (To-Dos)
- [ ] **Web Dashboard**: Create a simple React or HTML/JS frontend to visualize the candlestick chart, mark where the LLM bought/sold, and plot the equity curve in real-time.
- [ ] **Real-time Live Exchange Feed**: Replace the CSV data feed with a WebSocket connection to Binance or Bybit for live paper trading.
- [ ] **Technical Indicators**: Feed calculated indicators (RSI, MACD, Moving Averages) alongside raw prices to give the LLM better context.
- [ ] **Advanced Risk Management**: Dynamic stop-loss and trailing take-profit, informed by the LLM.
- [ ] **Structured Outputs**: Use strict JSON schemas/function calling in Ollama when the feature becomes stable, to guarantee the LLM outputs exact structures.
- [ ] **Save input tokens**: Improve current usage for faster calculations and cost reduction.
