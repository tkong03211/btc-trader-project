from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.models.volatility import VolatilityEstimator


def test_volatility_estimator_updates_and_stales() -> None:
    est = VolatilityEstimator(ewma_alpha=0.5, min_seconds_between_returns=0.0, stale_vol_secs=1.0)
    t0 = datetime.now(timezone.utc)
    est.update(price=100.0, ts=t0)
    assert est.get_estimate(t0) is None  # needs at least 2 points

    t1 = t0 + timedelta(seconds=1)
    est.update(price=110.0, ts=t1)
    v = est.get_estimate(t1)
    assert v is not None
    assert v.sigma_per_sqrt_sec > 0

    t2 = t1 + timedelta(seconds=2)
    assert est.get_estimate(t2) is None

