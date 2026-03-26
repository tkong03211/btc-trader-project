from __future__ import annotations

from datetime import datetime, timezone

from src.strategy.signal_engine import SignalEngine, MarketSpec, OrderBookTop


def _market_spec() -> MarketSpec:
    return MarketSpec(
        ticker="KXBTCD-26MAR2522-T71199.99",
        direction="above",
        strike=1199.99,
        expiry=datetime(2030, 1, 1, 0, tzinfo=timezone.utc),
    )


def test_signal_engine_enters_when_edge_large() -> None:
    engine = SignalEngine(min_entry_edge=0.01, exit_edge_threshold=0.0, fee_bps=0.0, price_slippage_bps=0.0)
    market = _market_spec()
    ob = OrderBookTop(bid=0.40, ask=0.42, updated_at=datetime.now(timezone.utc))
    # Model says YES=0.50 => edge vs ask 0.08 => enter.
    sig = engine.compute_signal(market=market, orderbook=ob, model_prob_yes=0.50, has_position=False)
    assert sig.decision == "enter_long"


def test_signal_engine_exits_when_edge_disappears() -> None:
    engine = SignalEngine(min_entry_edge=0.01, exit_edge_threshold=0.002, fee_bps=0.0, price_slippage_bps=0.0)
    market = _market_spec()
    ob = OrderBookTop(bid=0.46, ask=0.48, updated_at=datetime.now(timezone.utc))
    # With a position, compare to sell proceeds at bid (0.46).
    # If model_prob_yes drops to 0.461 => edge_sell ~ 0.001 => exit (<= threshold).
    sig = engine.compute_signal(market=market, orderbook=ob, model_prob_yes=0.461, has_position=True)
    assert sig.decision == "exit_long"

