from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


@dataclass
class Position:
    """
    Represents inventory for a YES share of a given contract.
    """

    market_ticker: str
    qty: int = 0
    avg_entry_price: float = 0.0


class PositionManager:
    """
    Tracks current inventory based on filled orders.
    """

    def __init__(self) -> None:
        self._positions: Dict[str, Position] = {}

    def get_position(self, market_ticker: str) -> Position:
        return self._positions.get(market_ticker) or Position(market_ticker=market_ticker)

    def has_position(self, market_ticker: str) -> bool:
        pos = self._positions.get(market_ticker)
        return pos is not None and pos.qty > 0

    def qty(self, market_ticker: str) -> int:
        pos = self._positions.get(market_ticker)
        return pos.qty if pos else 0

    def open_position(self, market_ticker: str, buy_qty: int, fill_price: float) -> None:
        if buy_qty <= 0:
            return
        pos = self._positions.get(market_ticker)
        if pos is None or pos.qty == 0:
            self._positions[market_ticker] = Position(
                market_ticker=market_ticker, qty=buy_qty, avg_entry_price=float(fill_price)
            )
            return

        # Weighted average entry price.
        new_qty = pos.qty + buy_qty
        pos.avg_entry_price = (pos.avg_entry_price * pos.qty + fill_price * buy_qty) / new_qty
        pos.qty = new_qty

    def close_position(self, market_ticker: str, sell_qty: int, fill_price: float) -> None:
        if sell_qty <= 0:
            return
        pos = self._positions.get(market_ticker)
        if pos is None:
            return
        pos.qty = max(0, pos.qty - sell_qty)
        if pos.qty == 0:
            # Remove to keep state tidy.
            self._positions.pop(market_ticker, None)

