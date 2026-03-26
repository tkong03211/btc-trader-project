from __future__ import annotations

import asyncio
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.config import AppConfig
from src.data.binance_client import BinanceClient, PriceTick
from src.data.kalshi_client import KalshiClient
from src.execution.order_manager import OrderManager
from src.execution.position_manager import PositionManager
from src.models.monte_carlo import MonteCarloSimulator
from src.models.volatility import VolatilityEstimator
from src.risk.risk_manager import RiskManager
from src.strategy.signal_engine import MarketSpec, SignalEngine, parse_kalshi_btc_market_ticker
from src.utils.logging_utils import configure_logging, get_logger, log_kv


logger = get_logger(__name__)


@dataclass
class _SharedMarketState:
    last_price: Optional[float] = None
    last_price_ts: Optional[datetime] = None
    last_orderbook: Optional[object] = None  # OrderBookTop but kept loose to avoid import cycles


class TradingApp:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        configure_logging(config.log_level)

        spec = parse_kalshi_btc_market_ticker(config.kalshi_market_ticker)
        if spec is None:
            raise ValueError(f"Could not parse Kalshi ticker: {config.kalshi_market_ticker}")
        self._market_spec: MarketSpec = spec

        # Shared state updated by ingestion tasks.
        self._shared = _SharedMarketState()
        self._shared_lock = asyncio.Lock()

        # Clients / components.
        self._binance = BinanceClient(ws_base_url=config.binance_ws_url, symbol=config.binance_symbol)
        self._kalshi = KalshiClient(
            config=config,
            btc_price_supplier=lambda: self._shared.last_price,
        )
        self._vol = VolatilityEstimator(
            ewma_alpha=config.ewma_alpha,
            min_seconds_between_returns=config.min_seconds_between_returns,
            stale_vol_secs=config.stale_vol_secs,
        )

        self._mc = MonteCarloSimulator(
            n_sims=config.mc_n_sims,
            seed=config.mc_seed,
            risk_free_rate_annual=config.risk_free_rate_annual,
        )
        self._signal_engine = SignalEngine(
            min_entry_edge=config.min_entry_edge,
            exit_edge_threshold=config.exit_edge_threshold,
            fee_bps=config.fee_bps,
            price_slippage_bps=config.price_slippage_bps,
        )

        self._positions = PositionManager()
        self._risk = RiskManager(config)
        self._orders = OrderManager(config=config, kalshi_client=self._kalshi)

        self._shutdown = asyncio.Event()
        self._active_order_lock = asyncio.Lock()

    async def _on_binance_tick(self, tick: PriceTick) -> None:
        async with self._shared_lock:
            self._shared.last_price = tick.price
            self._shared.last_price_ts = tick.updated_at
        self._vol.update(tick.price, tick.updated_at)

    async def _on_kalshi_orderbook(self, orderbook_top) -> None:
        async with self._shared_lock:
            self._shared.last_orderbook = orderbook_top

    def _is_price_fresh(self, now: datetime) -> bool:
        if self._shared.last_price is None or self._shared.last_price_ts is None:
            return False
        age = (now - self._shared.last_price_ts).total_seconds()
        return age <= self._config.max_price_age_secs

    def _get_orderbook_fresh(self, now: datetime):
        ob = self._shared.last_orderbook
        if ob is None:
            return None
        age = (now - ob.updated_at).total_seconds()
        if age > self._config.max_orderbook_age_secs:
            return None
        return ob

    def _open_positions_count(self) -> int:
        return 1 if self._positions.has_position(self._config.kalshi_market_ticker) else 0

    async def _enter_trade(self, model_prob_yes: float, orderbook) -> None:
        if self._positions.has_position(self._config.kalshi_market_ticker):
            return

        open_positions_count = self._open_positions_count()
        notional = self._config.max_notional_usd

        if not self._risk.can_trade_now(open_positions_count=open_positions_count, notional_usd=notional):
            return

        # Convert orderbook bid/ask to a limit price. We intentionally prefer
        # limit orders for cost control rather than crossing the spread blindly.
        offset_mult = 1.0 + (self._config.limit_price_offset_bps / 10000.0)
        limit_price = min(1.0, float(orderbook.ask) * offset_mult)  # buy at/near ask

        qty = self._risk.compute_entry_quantity(notional_usd=notional, price_yes=limit_price)
        if qty <= 0:
            return

        async with self._active_order_lock:
            order_id = await self._orders.place_limit_order(
                market_ticker=self._config.kalshi_market_ticker,
                side="buy",
                limit_price=limit_price,
                quantity=qty,
            )
            try:
                fill = await self._orders.wait_for_fill(
                    market_ticker=self._config.kalshi_market_ticker,
                    order_id=order_id,
                    timeout_secs=self._config.entry_order_timeout_secs,
                )
                if fill.status == "filled" and fill.filled_qty > 0:
                    self._positions.open_position(
                        market_ticker=self._config.kalshi_market_ticker,
                        buy_qty=fill.filled_qty,
                        fill_price=fill.avg_fill_price,
                    )
                    self._risk.record_success()
                    self._risk.mark_trade()
                    log_kv(logger, 20, "entered_position", order_id=order_id, filled_qty=fill.filled_qty, price=fill.avg_fill_price)
                else:
                    await self._orders.cancel_order(order_id=order_id)
                    self._risk.record_failure()
                    log_kv(logger, 30, "entry_not_filled", order_id=order_id, status=fill.status)
            except Exception:
                self._risk.record_failure()
                await self._orders.cancel_order(order_id=order_id)
                raise

    async def _exit_trade(self, orderbook) -> None:
        qty_held = self._positions.qty(self._config.kalshi_market_ticker)
        if qty_held <= 0:
            return

        offset_mult = 1.0 - (self._config.limit_price_offset_bps / 10000.0)
        limit_price = max(0.0, float(orderbook.bid) * offset_mult)  # sell at/near bid

        async with self._active_order_lock:
            order_id = await self._orders.place_limit_order(
                market_ticker=self._config.kalshi_market_ticker,
                side="sell",
                limit_price=limit_price,
                quantity=qty_held,
            )
            try:
                fill = await self._orders.wait_for_fill(
                    market_ticker=self._config.kalshi_market_ticker,
                    order_id=order_id,
                    timeout_secs=self._config.exit_order_timeout_secs,
                )
                if fill.status == "filled" and fill.filled_qty > 0:
                    self._positions.close_position(
                        market_ticker=self._config.kalshi_market_ticker,
                        sell_qty=fill.filled_qty,
                        fill_price=fill.avg_fill_price,
                    )
                    self._risk.record_success()
                    self._risk.mark_trade()
                    log_kv(logger, 20, "exited_position", order_id=order_id, filled_qty=fill.filled_qty, price=fill.avg_fill_price)
                else:
                    await self._orders.cancel_order(order_id=order_id)
                    self._risk.record_failure()
                    log_kv(logger, 30, "exit_not_filled", order_id=order_id, status=fill.status)
            except Exception:
                self._risk.record_failure()
                await self._orders.cancel_order(order_id=order_id)
                raise

    async def run_forever(self) -> None:
        """
        Start ingestion streams and continuously scan opportunities + manage open positions.
        """

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda s=sig: self._shutdown.set())
            except NotImplementedError:
                # Signal handlers may not be supported on some platforms.
                pass

        binance_task = asyncio.create_task(self._binance.stream_trades(self._on_binance_tick))
        kalshi_task = asyncio.create_task(
            self._kalshi.stream_orderbook_top(self._config.kalshi_market_ticker, self._on_kalshi_orderbook)
        )

        try:
            while not self._shutdown.is_set():
                now = datetime.now(timezone.utc)
                if not self._is_price_fresh(now):
                    await asyncio.sleep(self._config.scan_interval_secs)
                    continue

                orderbook = self._get_orderbook_fresh(now)
                if orderbook is None:
                    await asyncio.sleep(self._config.scan_interval_secs)
                    continue

                vol_est = self._vol.get_estimate(ts=now)
                if vol_est is None:
                    await asyncio.sleep(self._config.scan_interval_secs)
                    continue

                # Snapshot the shared price safely.
                async with self._shared_lock:
                    current_price = float(self._shared.last_price)  # type: ignore[arg-type]

                t_seconds = (self._market_spec.expiry - now).total_seconds()
                if t_seconds <= 0:
                    # Market resolved; stop trading.
                    logger.info("market_resolved_stop_trading", extra={"extras": {"ticker": self._market_spec.ticker}})
                    break

                mc = self._mc.estimate_probability(
                    current_price=current_price,
                    strike=self._market_spec.strike,
                    t_seconds=t_seconds,
                    sigma_per_sqrt_sec=vol_est.sigma_per_sqrt_sec,
                    direction=self._market_spec.direction,
                    expiry_time_buffer_secs=self._config.expiry_time_buffer_secs,
                )
                if mc is None:
                    await asyncio.sleep(self._config.scan_interval_secs)
                    continue

                has_pos = self._positions.has_position(self._config.kalshi_market_ticker)
                signal = self._signal_engine.compute_signal(
                    market=self._market_spec,
                    orderbook=orderbook,
                    model_prob_yes=mc.probability,
                    now=now,
                    has_position=has_pos,
                )

                if signal.decision == "enter_long":
                    await self._enter_trade(model_prob_yes=signal.model_prob_yes, orderbook=orderbook)
                elif signal.decision == "exit_long":
                    await self._exit_trade(orderbook=orderbook)

                await asyncio.sleep(self._config.scan_interval_secs)
        finally:
            self._shutdown.set()
            for t in (binance_task, kalshi_task):
                t.cancel()
            await asyncio.gather(binance_task, kalshi_task, return_exceptions=True)


def main() -> None:
    config = AppConfig.from_env()
    app = TradingApp(config=config)
    asyncio.run(app.run_forever())


if __name__ == "__main__":
    main()

