from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


def _env_float(name: str, default: float) -> float:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return float(v)


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return int(v)


def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class AppConfig:
    """
    Application configuration loaded from environment variables.

    This sample repo avoids committing secrets; use environment variables at runtime.
    """

    # Core
    log_level: str
    paper_trading: bool
    scan_interval_secs: float

    # Data freshness
    max_price_age_secs: float
    max_orderbook_age_secs: float

    # Kalshi
    kalshi_base_url: str
    kalshi_ws_url: str
    kalshi_api_key: Optional[str]
    kalshi_api_secret: Optional[str]
    kalshi_market_ticker: str

    # Binance
    binance_ws_url: str
    binance_symbol: str

    # Volatility model (EWMA)
    ewma_alpha: float
    min_seconds_between_returns: float
    stale_vol_secs: float

    # Monte Carlo
    mc_n_sims: int
    mc_seed: int
    risk_free_rate_annual: float
    expiry_time_buffer_secs: float

    # Strategy / signal thresholds
    min_entry_edge: float
    exit_edge_threshold: float
    trade_cooldown_secs: float
    fee_bps: float
    price_slippage_bps: float
    entry_order_timeout_secs: float
    exit_order_timeout_secs: float

    # Limit order pricing logic
    limit_price_offset_bps: float

    # Risk controls
    max_open_positions: int
    max_shares_per_position: int
    max_notional_usd: float
    max_consecutive_failures: int
    kill_switch: bool

    @staticmethod
    def from_env() -> "AppConfig":
        return AppConfig(
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            paper_trading=_env_bool("PAPER_TRADING", True),
            scan_interval_secs=_env_float("SCAN_INTERVAL_SECS", 2.0),
            max_price_age_secs=_env_float("MAX_PRICE_AGE_SECS", 10.0),
            max_orderbook_age_secs=_env_float("MAX_ORDERBOOK_AGE_SECS", 10.0),
            kalshi_base_url=os.getenv("KALSHI_BASE_URL", "https://api.kalshi.com"),
            kalshi_ws_url=os.getenv("KALSHI_WS_URL", "wss://api.kalshi.com"),
            kalshi_api_key=os.getenv("KALSHI_API_KEY"),
            kalshi_api_secret=os.getenv("KALSHI_API_SECRET"),
            kalshi_market_ticker=os.getenv(
                "KALSHI_MARKET_TICKER", "KXBTCD-26MAR2522-T71199.99"
            ),
            binance_ws_url=os.getenv("BINANCE_WS_URL", "wss://stream.binance.com:9443/ws"),
            binance_symbol=os.getenv("BINANCE_SYMBOL", "btcusdt"),
            ewma_alpha=_env_float("EWMA_ALPHA", 0.02),
            min_seconds_between_returns=_env_float("MIN_SECONDS_BETWEEN_RETURNS", 0.05),
            stale_vol_secs=_env_float("STALE_VOL_SECS", 60.0),
            mc_n_sims=_env_int("MC_N_SIMS", 20000),
            mc_seed=_env_int("MC_SEED", 7),
            risk_free_rate_annual=_env_float("RISK_FREE_RATE_ANNUAL", 0.0),
            expiry_time_buffer_secs=_env_float("EXPIRY_TIME_BUFFER_SECS", 0.0),
            min_entry_edge=_env_float("MIN_ENTRY_EDGE", 0.01),
            exit_edge_threshold=_env_float("EXIT_EDGE_THRESHOLD", 0.002),
            trade_cooldown_secs=_env_float("TRADE_COOLDOWN_SECS", 20.0),
            fee_bps=_env_float("FEE_BPS", 2.0),
            price_slippage_bps=_env_float("PRICE_SLIPPAGE_BPS", 2.0),
            entry_order_timeout_secs=_env_float("ENTRY_ORDER_TIMEOUT_SECS", 15.0),
            exit_order_timeout_secs=_env_float("EXIT_ORDER_TIMEOUT_SECS", 15.0),
            limit_price_offset_bps=_env_float("LIMIT_PRICE_OFFSET_BPS", 0.0),
            max_open_positions=_env_int("MAX_OPEN_POSITIONS", 1),
            max_shares_per_position=_env_int("MAX_SHARES_PER_POSITION", 10),
            max_notional_usd=_env_float("MAX_NOTIONAL_USD", 5000.0),
            max_consecutive_failures=_env_int("MAX_CONSECUTIVE_FAILURES", 10),
            kill_switch=_env_bool("KILL_SWITCH", False),
        )

