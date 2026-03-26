from __future__ import annotations

from src.models.monte_carlo import MonteCarloSimulator


def test_monte_carlo_sigma_zero_above() -> None:
    sim = MonteCarloSimulator(n_sims=1000, seed=1)
    # sigma=0 => price at expiry is deterministic and equals current.
    p = sim.estimate_probability(
        current_price=120.0,
        strike=100.0,
        t_seconds=3600.0,
        sigma_per_sqrt_sec=0.0,
        direction="above",
    )
    assert p is not None
    assert p.probability == 1.0

    p2 = sim.estimate_probability(
        current_price=80.0,
        strike=100.0,
        t_seconds=3600.0,
        sigma_per_sqrt_sec=0.0,
        direction="above",
    )
    assert p2 is not None
    assert p2.probability == 0.0

