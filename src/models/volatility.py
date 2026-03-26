from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class VolatilityEstimate:
    """
    Volatility represented as sigma per sqrt(second).

    If log-returns are modeled as:
        dlog S = sigma * dW
    then Var(log S_T - log S_0) = sigma^2 * T_seconds.
    """

    sigma_per_sqrt_sec: float
    updated_at: datetime


class VolatilityEstimator:
    """
    Streaming volatility estimator using an EWMA model on squared log returns.

    This is intentionally lightweight and production-minded (staleness handling, dt checks).
    """

    def __init__(
        self,
        ewma_alpha: float,
        min_seconds_between_returns: float,
        stale_vol_secs: float,
    ) -> None:
        if not (0.0 < ewma_alpha <= 1.0):
            raise ValueError("ewma_alpha must be in (0, 1].")
        self._alpha = ewma_alpha
        self._min_dt = min_seconds_between_returns
        self._stale_vol_secs = stale_vol_secs

        self._last_price: Optional[float] = None
        self._last_ts: Optional[datetime] = None
        self._var_per_sec: Optional[float] = None  # sigma^2 per second
        self._updated_at: Optional[datetime] = None

    def update(self, price: float, ts: Optional[datetime] = None) -> None:
        """
        Update estimator with a new price observation.
        """

        if price <= 0:
            return

        now = ts or _utc_now()
        if self._last_price is None or self._last_ts is None:
            self._last_price = price
            self._last_ts = now
            return

        dt = (now - self._last_ts).total_seconds()
        if dt < self._min_dt:
            # Avoid instability from duplicate/out-of-order ticks.
            return
        if dt <= 0:
            self._last_price = price
            self._last_ts = now
            return

        # Log return for the interval.
        r = math.log(price / self._last_price)

        # Update EWMA variance per second:
        #   var_per_sec <- (1-a)*var_per_sec + a*(r^2/dt)
        inst_var_per_sec = (r * r) / dt
        if self._var_per_sec is None:
            self._var_per_sec = inst_var_per_sec
        else:
            self._var_per_sec = (1.0 - self._alpha) * self._var_per_sec + self._alpha * inst_var_per_sec

        self._last_price = price
        self._last_ts = now
        self._updated_at = now

    def get_estimate(self, ts: Optional[datetime] = None) -> Optional[VolatilityEstimate]:
        """
        Return latest volatility estimate, or None if stale/not ready.
        """

        if self._var_per_sec is None or self._updated_at is None:
            return None

        now = ts or _utc_now()
        age = (now - self._updated_at).total_seconds()
        if age > self._stale_vol_secs:
            return None

        sigma_per_sqrt_sec = math.sqrt(max(self._var_per_sec, 0.0))
        return VolatilityEstimate(
            sigma_per_sqrt_sec=sigma_per_sqrt_sec,
            updated_at=self._updated_at,
        )

