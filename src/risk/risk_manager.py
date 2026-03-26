from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict

from src.config import AppConfig


@dataclass
class RiskState:
    consecutive_failures: int = 0
    last_trade_ts: float = 0.0


class RiskManager:
    """
    Minimal risk controls suitable for a trading-system code sample.
    """

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._state = RiskState()

    def is_killed(self) -> bool:
        return bool(self._config.kill_switch) or self._state.consecutive_failures >= self._config.max_consecutive_failures

    def record_failure(self) -> None:
        self._state.consecutive_failures += 1

    def record_success(self) -> None:
        self._state.consecutive_failures = 0

    def can_trade_now(self, open_positions_count: int, notional_usd: float) -> bool:
        if self.is_killed():
            return False
        if open_positions_count >= self._config.max_open_positions:
            return False
        if notional_usd > self._config.max_notional_usd:
            return False
        now = time.time()
        if now - self._state.last_trade_ts < self._config.trade_cooldown_secs:
            return False
        return True

    def mark_trade(self) -> None:
        self._state.last_trade_ts = time.time()

    def compute_entry_quantity(self, notional_usd: float, price_yes: float) -> int:
        """
        Compute number of shares to buy based on notional_usd and configured limits.

        `price_yes` is interpreted as the YES probability in [0, 1]. In real Kalshi trading,
        the dollar cost per share is not equal to probability; this code sample treats it
        as a proxy so it remains runnable.
        """

        if price_yes <= 0:
            return 0
        qty = int(notional_usd / price_yes)
        qty = max(qty, 0)
        qty = min(qty, self._config.max_shares_per_position)
        return qty

