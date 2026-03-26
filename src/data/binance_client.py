from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import aiohttp
import websockets


@dataclass(frozen=True)
class PriceTick:
    price: float
    updated_at: datetime


class BinanceClient:
    """
    Binance BTC price streaming client.

    For this code sample we stream `btcusdt@trade` for spot price ticks.
    """

    def __init__(self, ws_base_url: str, symbol: str) -> None:
        self._ws_base_url = ws_base_url.rstrip("/")
        self._symbol = symbol.lower()

    def _ws_url(self) -> str:
        # Example: wss://stream.binance.com:9443/ws/btcusdt@trade
        return f"{self._ws_base_url}/{self._symbol}@trade"

    async def get_last_price_rest(self) -> Optional[PriceTick]:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={self._symbol.upper()}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
                    price = float(data["price"])
                    return PriceTick(price=price, updated_at=datetime.now(timezone.utc))
            except Exception:
                return None

    async def stream_trades(
        self,
        on_tick: Callable[[PriceTick], Awaitable[None]],
        reconnect_delay_secs: float = 3.0,
    ) -> None:
        """
        Continuously stream trades and call `on_tick` for each price update.
        """

        while True:
            try:
                async with websockets.connect(self._ws_url(), ping_interval=20, ping_timeout=20) as ws:
                    async for message in ws:
                        try:
                            payload = json.loads(message)
                            # Binance stream trade payload uses key "p" for price.
                            price = float(payload["p"])
                            tick = PriceTick(price=price, updated_at=datetime.now(timezone.utc))
                            await on_tick(tick)
                        except Exception:
                            # Ignore malformed ticks; keep stream alive.
                            continue
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(reconnect_delay_secs)

