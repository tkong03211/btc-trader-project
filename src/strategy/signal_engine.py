from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Literal

from src.utils.logging_utils import get_logger


OutcomeDirection = Literal["above", "below"]
EdgeDecision = Literal["enter_long", "exit_long", "hold"]

logger = get_logger(__name__)


@dataclass(frozen=True)
class MarketSpec:
    """
    Parsed contract spec needed for modeling.

    For a Kalshi binary contract, the YES side typically corresponds to either
    "BTC finishes above strike" or "BTC finishes below strike".
    """

    ticker: str
    direction: OutcomeDirection  # "above" means YES pays when S_T > strike
    strike: float
    expiry: datetime


@dataclass(frozen=True)
class OrderBookTop:
    bid: float
    ask: float
    updated_at: datetime


@dataclass(frozen=True)
class Signal:
    decision: EdgeDecision
    edge: float
    model_prob_yes: float
    market_prob_yes: float
    buy_price_yes: float
    sell_price_yes: float


def parse_kalshi_btc_market_ticker(ticker: str) -> Optional[MarketSpec]:
    """
    Parse `KXBTCD-26MAR2522-T71199.99`-style tickers.

    This is a best-effort parser for the provided example and is intentionally strict.
    TODO: verify Kalshi's exact ticker conventions for real deployments.
    """

    # Example: KXBTCD-26MAR2522-T71199.99
    # We assume:
    # - prefix - expiry_token - strike_token
    # - expiry_token matches: ddMMMyyHH (all-caps month)
    #   e.g. 26MAR2522 => 2025-03-26 22:00 UTC
    # - strike_token begins with 'T' followed by a single digit precision code,
    #   then the numeric strike, e.g. T71199.99 => strike=1199.99
    #
    # TODO: verify these conventions for real Kalshi contracts.
    parts = ticker.split("-")
    if len(parts) != 3:
        return None

    _prefix, expiry_token, strike_token = parts

    # expiry_token like 26MAR2522 (ddMMMyyHH)
    if len(expiry_token) != 9:
        # Some Kalshi tickers omit hour; keep this strict for the sample.
        return None
    day = int(expiry_token[0:2])
    mon_str = expiry_token[2:5]
    yy = int(expiry_token[5:7])
    hour = int(expiry_token[7:9])
    year = 2000 + yy

    months = {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AUG": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DEC": 12,
    }
    if mon_str.upper() not in months:
        return None

    expiry = datetime(year, months[mon_str.upper()], day, int(hour), tzinfo=timezone.utc)

    # strike_token like T71199.99
    if not strike_token.startswith("T") or len(strike_token) < 3:
        return None
    # Drop 'T' and the next digit precision code.
    try:
        strike = float(strike_token[2:])
    except ValueError:
        # Fallback: parse trailing numeric segment.
        s = strike_token
        numeric = "".join(ch for ch in s if ch.isdigit() or ch == ".")
        if numeric:
            try:
                strike = float(numeric)
            except ValueError:
                return None
        else:
            return None

    # Direction:
    # In Kalshi's naming, binary "above" vs "below" may be encoded elsewhere.
    # For the sample contract, we default to "above" because the provided edge logic
    # expects a YES payout when finishing above strike.
    # TODO: map ticker naming to "above"/"below" correctly for real deployments.
    direction: OutcomeDirection = "above"

    return MarketSpec(ticker=ticker, direction=direction, strike=strike, expiry=expiry)


class SignalEngine:
    def __init__(
        self,
        min_entry_edge: float,
        exit_edge_threshold: float,
        fee_bps: float,
        price_slippage_bps: float,
    ) -> None:
        self._min_entry_edge = float(min_entry_edge)
        self._exit_edge_threshold = float(exit_edge_threshold)
        self._fee_bps = float(fee_bps)
        self._slip_bps = float(price_slippage_bps)

    def compute_signal(
        self,
        market: MarketSpec,
        orderbook: OrderBookTop,
        model_prob_yes: float,
        now: Optional[datetime] = None,
        has_position: bool = False,
    ) -> Signal:
        """
        Compute enter/exit decision based on edge between model and market implied probability.

        Assumptions for code sample:
        - Kalshi contract price is interpreted as YES probability in [0, 1]
        - To buy YES, effective price = ask with fee+slippage
        - To sell YES, effective price = bid with (fee+slippage)
        """

        bid = max(0.0, float(orderbook.bid))
        ask = max(0.0, float(orderbook.ask))
        if bid <= 0 or ask <= 0 or bid > ask:
            # Invalid orderbook for pricing probabilities.
            edge = float("-inf")
            return Signal(
                decision="hold",
                edge=edge,
                model_prob_yes=model_prob_yes,
                market_prob_yes=float("nan"),
                buy_price_yes=float("nan"),
                sell_price_yes=float("nan"),
            )

        mid = 0.5 * (bid + ask)

        fee_mult = 1.0 + (self._fee_bps / 10000.0)
        slip_mult = 1.0 + (self._slip_bps / 10000.0)
        buy_price_yes = min(1.0, ask * fee_mult * slip_mult)
        sell_price_yes = max(0.0, bid / (fee_mult * slip_mult))
        # Note: sell_price is conservative: assume fees reduce proceeds.

        market_prob_yes = float(mid)
        edge_entry = model_prob_yes - buy_price_yes
        edge_sell = model_prob_yes - sell_price_yes

        if not has_position:
            decision: EdgeDecision = "enter_long" if edge_entry >= self._min_entry_edge else "hold"
            edge = edge_entry
        else:
            # If edge has decayed (model is no longer sufficiently above the sell price),
            # then exit.
            decision = "exit_long" if edge_sell <= self._exit_edge_threshold else "hold"
            edge = edge_sell

        return Signal(
            decision=decision,
            edge=float(edge),
            model_prob_yes=float(model_prob_yes),
            market_prob_yes=float(market_prob_yes),
            buy_price_yes=float(buy_price_yes),
            sell_price_yes=float(sell_price_yes),
        )

