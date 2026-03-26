from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

import numpy as np


OutcomeDirection = Literal["above", "below"]


@dataclass(frozen=True)
class MonteCarloResult:
    probability: float
    n_sims: int


class MonteCarloSimulator:
    """
    Monte Carlo simulator for P(price_T > strike) or P(price_T < strike).

    We model BTC spot as geometric Brownian motion:
        dlog S = (mu - 0.5*sigma^2) dt + sigma dW
    where:
        sigma is sigma_per_sqrt_sec
        dt is measured in seconds
    """

    def __init__(self, n_sims: int, seed: int = 7, risk_free_rate_annual: float = 0.0) -> None:
        if n_sims <= 0:
            raise ValueError("n_sims must be positive")
        self._n_sims = n_sims
        self._rng = np.random.default_rng(seed)
        self._r_annual = risk_free_rate_annual

    def estimate_probability(
        self,
        current_price: float,
        strike: float,
        t_seconds: float,
        sigma_per_sqrt_sec: float,
        direction: OutcomeDirection,
        expiry_time_buffer_secs: float = 0.0,
    ) -> Optional[MonteCarloResult]:
        if current_price <= 0 or strike <= 0:
            return None

        # Buffer shifts the effective horizon to match when Kalshi resolves.
        effective_t = t_seconds - expiry_time_buffer_secs
        if effective_t <= 0:
            if direction == "above":
                return MonteCarloResult(probability=float(current_price > strike), n_sims=0)
            return MonteCarloResult(probability=float(current_price < strike), n_sims=0)

        sigma = max(sigma_per_sqrt_sec, 0.0)
        t = float(effective_t)

        # Convert annual risk-free rate to per-second drift term.
        # r_annual is assumed continuously compounded.
        # Use 365 days for conversion; for a code sample this is sufficient.
        seconds_per_year = 365.0 * 24.0 * 3600.0
        r = self._r_annual / seconds_per_year

        # GBM log-return distribution.
        # ln(S_T/S_0) ~ Normal((r - 0.5*sigma^2)*t, sigma^2*t)
        mean = (r - 0.5 * sigma * sigma) * t
        std = sigma * np.sqrt(t)

        z = self._rng.standard_normal(self._n_sims)
        log_returns = mean + std * z
        s_t = current_price * np.exp(log_returns)

        if direction == "above":
            prob = float(np.mean(s_t > strike))
        else:
            prob = float(np.mean(s_t < strike))

        return MonteCarloResult(probability=prob, n_sims=self._n_sims)

