from __future__ import annotations

import asyncio
import hmac
import hashlib
import json
import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import aiohttp
import websockets

from src.config import AppConfig
from src.strategy.signal_engine import OrderBookTop, parse_kalshi_btc_market_ticker


class KalshiClient:
    """
    Kalshi market data + trading client.

    This repository is public-friendly: real Kalshi trading endpoints are left as TODO stubs.
    If `PAPER_TRADING=1`, the client generates a synthetic order book so the rest of the system
    can be run and discussed without API credentials.
    """

    def __init__(
        self,
        config: AppConfig,
        btc_price_supplier: Optional[Callable[[], Optional[float]]] = None,
    ) -> None:
        self._config = config
        self._btc_price_supplier = btc_price_supplier
        self._paper_rng = random.Random(1234)
        self._last_orderbook: Optional[OrderBookTop] = None

    async def get_orderbook_top(self, market_ticker: str) -> Optional[OrderBookTop]:
        """
        Return latest (bid, ask) for the contract.

        In paper mode, this synthesizes a top-of-book from the latest supplied BTC price.
        In real mode, this should query Kalshi's REST/WebSocket state.
        """

        if self._config.paper_trading:
            ob = self._paper_synth_orderbook(market_ticker=market_ticker)
            self._last_orderbook = ob
            return ob

        # TODO: Replace with Kalshi REST call to fetch orderbook best bid/ask.
        raise NotImplementedError(
            "Real Kalshi orderbook retrieval is not implemented in this public sample."
        )

    def _paper_synth_orderbook(self, market_ticker: str) -> OrderBookTop:
        if self._btc_price_supplier is None:
            # If no supplier is available, return a neutral book.
            mid = 0.5
        else:
            btc = self._btc_price_supplier()
            if btc is None or btc <= 0:
                mid = 0.5
            else:
                spec = parse_kalshi_btc_market_ticker(market_ticker)
                if spec is None:
                    mid = 0.5
                else:
                    # Simple synthetic mapping: tilt probability with price vs strike.
                    # This is not economically accurate; it's just realistic enough to
                    # produce edges between model and market.
                    x = (btc / spec.strike) - 1.0
                    scale = 1.8  # controls steepness
                    bias = float(os.getenv("PAPER_IMPLIED_PROB_BIAS", "0.0"))
                    noise = self._paper_rng.normalvariate(0.0, 0.02)
                    mid = 0.5 + bias + scale * x + noise

        mid = max(0.01, min(0.99, float(mid)))
        spread = max(0.002, float(os.getenv("PAPER_SPREAD_BPS", "20")) / 10000.0)  # 20 bps -> 0.0020
        half = spread / 2.0
        bid = max(0.0, mid - half)
        ask = min(1.0, mid + half)
        now = datetime.now(timezone.utc)
        return OrderBookTop(bid=bid, ask=ask, updated_at=now)

    async def stream_orderbook_top(
        self,
        market_ticker: str,
        on_update: Callable[[OrderBookTop], Awaitable[None]],
        poll_interval_secs: float = 1.0,
    ) -> None:
        """
        Continuously emit orderbook top updates.

        In paper mode we emit periodic synthetic order book updates.
        In real mode this should be driven by Kalshi WebSockets or REST polling.
        """

        while True:
            try:
                ob = await self.get_orderbook_top(market_ticker=market_ticker)
                if ob is not None:
                    await on_update(ob)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Keep running; main will detect staleness.
                await asyncio.sleep(poll_interval_secs)

            await asyncio.sleep(poll_interval_secs)

    # --- Auth helpers (real trading TODO) ---
    def _kalshi_signature(self, method: str, path: str, body: str, nonce: str) -> str:
        """
        Kalshi authentication typically uses HMAC signatures.

        TODO: verify Kalshi's exact signing procedure for the current API version.
        """
        secret = (self._config.kalshi_api_secret or "").encode("utf-8")
        msg = f"{nonce}{method}{path}{body}".encode("utf-8")
        return hmac.new(secret, msg, hashlib.sha256).hexdigest()

