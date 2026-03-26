## Kalshi BTC Prediction Market Trader (Code Sample for MLH Fellowship)

This repository is a Python-based automated trading system for Bitcoin-related prediction markets on Kalshi.
It continuously ingests live BTC price data from Binance and Kalshi market prices, continuously updates a rolling
volatility estimate from the BTC stream, then runs Monte Carlo simulations to estimate fair outcome probabilities
for a given Kalshi contract. When the model-implied probability diverges sufficiently from the market-implied
probability, the system enters a trade; when the discrepancy decays, it exits using limit-order logic.

### What this code sample does
1. Streams BTC spot prices from Binance (WebSocket; REST fallback included as a lightweight utility).
2. Estimates volatility online using an EWMA model on log returns.
3. Runs Monte Carlo simulations (GBM) to estimate `P(event)` for a binary contract.
4. Converts the Kalshi top-of-book into a market-implied probability and computes an edge.
5. Enters with a limit order when the edge exceeds a configured threshold.
6. Exits with a limit order when the edge decays below an exit threshold.
7. Applies basic risk controls (position sizing, max positions, notional caps, cooldown, kill switch).

### Public repo note about Kalshi
Kalshi trading/auth endpoints are intentionally stubbed in this public code sample.
By default, the app runs in `PAPER_TRADING=1` mode, where `KalshiClient` synthesizes a realistic order book
top using Binance BTC as an input. This makes the project runnable for demonstration and interviews.

When you want to trade for real:
- Implement real Kalshi orderbook retrieval in `src/data/kalshi_client.py` (TODO).
- Implement real Kalshi order placement/status in `src/execution/order_manager.py` (TODO).
- Validate the Kalshi contract parsing rules and outcome mapping in `src/strategy/signal_engine.py` (TODO).

### Project structure
The system is split into clean modules:
- `src/main.py`: application entry point; orchestrates async tasks and the trading loop
- `src/config.py`: environment-based configuration (no secrets committed)
- `src/data/binance_client.py`: Binance streaming + REST fallback helper
- `src/data/kalshi_client.py`: Kalshi auth/market data stub + paper mode order book synthesis
- `src/models/volatility.py`: EWMA rolling volatility estimator on log returns
- `src/models/monte_carlo.py`: GBM Monte Carlo probability engine
- `src/strategy/signal_engine.py`: parses the market ticker (best-effort), edge detection, enter/exit logic
- `src/execution/order_manager.py`: limit-order placement + paper-fill simulation (real mode TODO)
- `src/execution/position_manager.py`: inventory tracking for the current contract
- `src/risk/risk_manager.py`: risk checks, cooldown, max position/notional controls
- `src/utils/logging_utils.py`: structured logging helpers
- `tests/`: unit tests for volatility, Monte Carlo, and signal logic

### How to run (paper mode demo)
1. Create a virtual environment:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run:
   - `PAPER_TRADING=1 python -m src.main`

You should see JSON-ish logs (if `LOG_JSON=1`) or standard console logs indicating entries/exits.

### Key environment variables
- `KALSHI_MARKET_TICKER`: default `KXBTCD-26MAR2522-T71199.99`
- `PAPER_TRADING`: default `1` (synthesizes order book)
- `LOG_LEVEL`: default `INFO`
- `BINANCE_SYMBOL`: default `btcusdt`
- `MAX_PRICE_AGE_SECS`: how stale the latest Binance tick can be
- `MAX_ORDERBOOK_AGE_SECS`: how stale the latest Kalshi top-of-book can be
- `MIN_ENTRY_EDGE`: minimum model-market edge to enter
- `EXIT_EDGE_THRESHOLD`: exit threshold when holding a position
- `KILL_SWITCH`: stop trading after repeated failures (see `MAX_CONSECUTIVE_FAILURES`)

### Kalshi-specific TODOs to complete for real trading
1. Contract parsing and direction mapping:
   - `parse_kalshi_btc_market_ticker()` currently defaults to `direction="above"`.
   - TODO: map Kalshi ticker naming to `above` vs `below` and YES payout side precisely.
2. Real Kalshi market data:
   - `KalshiClient.get_orderbook_top()` is a TODO for non-paper mode.
3. Real Kalshi order execution:
   - `OrderManager.place_limit_order()` raises `NotImplementedError` for non-paper mode.
4. Order sizing and price-to-cost conversion:
   - This sample treats Kalshi contract price as a proxy for probability in `[0,1]` and uses it
     to compute a share quantity from `MAX_NOTIONAL_USD`. In real trading you must implement
     Kalshi’s exact contract pricing/cost conventions.

