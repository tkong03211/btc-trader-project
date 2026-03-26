from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Literal, Optional

from src.config import AppConfig
from src.data.kalshi_client import KalshiClient
from src.strategy.signal_engine import OrderBookTop
from src.utils.logging_utils import get_logger


OrderSide = Literal["buy", "sell"]
OrderResultStatus = Literal["filled", "open", "cancelled", "expired"]

logger = get_logger(__name__)


@dataclass(frozen=True)
class OrderFill:
    order_id: str
    status: OrderResultStatus
    filled_qty: int
    avg_fill_price: float


@dataclass
class _PaperOrder:
    order_id: str
    side: OrderSide
    price: float
    qty: int
    created_at: float
    cancelled: bool = False
    filled_qty: int = 0
    avg_fill_price: float = 0.0


class OrderManager:
    """
    Places and monitors limit orders.

    In `PAPER_TRADING=1` mode, the manager simulates fills against the latest order book top.
    In non-paper mode, it delegates to Kalshi REST endpoints (stubbed in this sample).
    """

    def __init__(self, config: AppConfig, kalshi_client: KalshiClient) -> None:
        self._config = config
        self._kalshi = kalshi_client
        self._paper_orders: Dict[str, _PaperOrder] = {}
        self._lock = asyncio.Lock()

    async def place_limit_order(
        self,
        market_ticker: str,
        side: OrderSide,
        limit_price: float,
        quantity: int,
    ) -> str:
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        if limit_price <= 0:
            raise ValueError("limit_price must be positive")

        order_id = uuid.uuid4().hex

        if self._config.paper_trading:
            async with self._lock:
                self._paper_orders[order_id] = _PaperOrder(
                    order_id=order_id,
                    side=side,
                    price=float(limit_price),
                    qty=int(quantity),
                    created_at=time.time(),
                )
            logger.info(
                "paper_place_limit_order",
                extra={"extras": {"order_id": order_id, "side": side, "price": limit_price, "qty": quantity}},
            )
            return order_id

        # Real Kalshi mode (stubbed)
        raise NotImplementedError("Real Kalshi trading is not implemented in this public sample.")

    async def cancel_order(self, order_id: str) -> bool:
        if self._config.paper_trading:
            async with self._lock:
                o = self._paper_orders.get(order_id)
                if not o or o.filled_qty > 0 or o.cancelled:
                    return False
                o.cancelled = True
                return True
        return False

    async def wait_for_fill(
        self,
        market_ticker: str,
        order_id: str,
        timeout_secs: float,
        poll_interval_secs: float = 0.5,
    ) -> OrderFill:
        """
        Poll until filled/cancelled/timeout.

        For paper mode, we fill when limit crosses against order book top:
        - buy fills when limit_price >= ask
        - sell fills when limit_price <= bid
        """

        deadline = time.time() + float(timeout_secs)
        while True:
            async with self._lock:
                o = self._paper_orders.get(order_id)
                if not o:
                    return OrderFill(order_id=order_id, status="cancelled", filled_qty=0, avg_fill_price=0.0)
                if o.cancelled:
                    return OrderFill(order_id=order_id, status="cancelled", filled_qty=0, avg_fill_price=0.0)
                if o.filled_qty > 0:
                    return OrderFill(
                        order_id=order_id,
                        status="filled",
                        filled_qty=o.filled_qty,
                        avg_fill_price=o.avg_fill_price,
                    )

            if time.time() >= deadline:
                return OrderFill(order_id=order_id, status="expired", filled_qty=0, avg_fill_price=0.0)

            if self._config.paper_trading:
                ob: Optional[OrderBookTop] = await self._kalshi.get_orderbook_top(market_ticker=market_ticker)
                if ob is not None:
                    should_fill = (o.side == "buy" and o.price >= ob.ask) or (o.side == "sell" and o.price <= ob.bid)
                    if should_fill:
                        # Fill at the more conservative price (still within limit):
                        # - buy fills at ask
                        # - sell fills at bid
                        fill_price = ob.ask if o.side == "buy" else ob.bid
                        async with self._lock:
                            oo = self._paper_orders.get(order_id)
                            if oo and not oo.cancelled and oo.filled_qty == 0:
                                oo.filled_qty = oo.qty
                                oo.avg_fill_price = float(fill_price)
                        continue

            await asyncio.sleep(poll_interval_secs)

    async def get_order_status(self, order_id: str) -> Optional[OrderFill]:
        if not self._config.paper_trading:
            return None
        async with self._lock:
            o = self._paper_orders.get(order_id)
            if not o:
                return None
            if o.filled_qty > 0:
                return OrderFill(order_id=order_id, status="filled", filled_qty=o.filled_qty, avg_fill_price=o.avg_fill_price)
            if o.cancelled:
                return OrderFill(order_id=order_id, status="cancelled", filled_qty=0, avg_fill_price=0.0)
            return OrderFill(order_id=order_id, status="open", filled_qty=0, avg_fill_price=0.0)

