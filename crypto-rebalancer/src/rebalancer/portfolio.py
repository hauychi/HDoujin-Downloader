"""Pure rebalancing math. No network, no I/O — everything is unit-testable."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

# Binance accepts quoteOrderQty with up to 8 decimal places. We quantize to
# this grid so that buy notionals don't send ambiguous high-precision values.
_NOTIONAL_QUANT = Decimal("0.00000001")


@dataclass(frozen=True)
class SymbolFilters:
    """Binance symbol filters relevant to order sizing."""
    step_size: Decimal
    tick_size: Decimal
    min_notional: Decimal


@dataclass(frozen=True)
class Trade:
    symbol: str            # base asset (e.g. "BTC")
    pair: str              # trading pair (e.g. "BTCUSDT")
    side: str              # "BUY" or "SELL"
    quantity: Decimal      # base asset amount. Authoritative for SELL; estimate for BUY.
    notional: Decimal      # quote amount. Authoritative for BUY (quoteOrderQty); estimate for SELL.


def compute_weights(
    balances: dict[str, Decimal],
    prices: dict[str, Decimal],
    asset_symbols: list[str],
    quote: str,
) -> tuple[Decimal, dict[str, Decimal]]:
    """Return (total_value_in_quote, {symbol_or_quote: weight}).

    Only assets listed in `asset_symbols` plus the quote itself are considered.
    Balances of other coins are ignored for weighting.
    """
    values: dict[str, Decimal] = {}
    for sym in asset_symbols:
        qty = balances.get(sym, Decimal(0))
        px = prices.get(_pair(sym, quote))
        if px is None:
            raise ValueError(f"missing price for {_pair(sym, quote)}")
        values[sym] = qty * px
    values[quote] = balances.get(quote, Decimal(0))

    total = sum(values.values(), start=Decimal(0))
    if total <= 0:
        return Decimal(0), {k: Decimal(0) for k in values}

    weights = {k: (v / total) for k, v in values.items()}
    return total, weights


def compute_drifts(
    weights: dict[str, Decimal],
    targets: dict[str, float],
) -> dict[str, Decimal]:
    """drift = current_weight - target_weight, per asset in `targets`."""
    return {
        sym: weights.get(sym, Decimal(0)) - Decimal(str(target))
        for sym, target in targets.items()
    }


def needs_rebalance(drifts: dict[str, Decimal], threshold: float) -> bool:
    t = Decimal(str(threshold))
    return any(abs(d) >= t for d in drifts.values())


def compute_trades(
    total_value: Decimal,
    weights: dict[str, Decimal],
    targets: dict[str, float],
    prices: dict[str, Decimal],
    filters: dict[str, SymbolFilters],
    quote: str,
    max_trade_quote: float,
) -> list[Trade]:
    """Return the list of trades that would move the portfolio toward target.

    Sells are emitted before buys so that quote-currency proceeds from sells
    fund subsequent buys in the same tick.
    """
    max_leg = Decimal(str(max_trade_quote))
    sells: list[Trade] = []
    buys: list[Trade] = []

    for sym, target in targets.items():
        pair = _pair(sym, quote)
        price = prices[pair]
        filt = filters[pair]

        current_value = weights.get(sym, Decimal(0)) * total_value
        target_value = Decimal(str(target)) * total_value
        delta_value = target_value - current_value     # positive = need to buy

        # Clamp to per-trade cap.
        if delta_value > max_leg:
            delta_value = max_leg
        elif delta_value < -max_leg:
            delta_value = -max_leg

        if delta_value == 0:
            continue

        side = "BUY" if delta_value > 0 else "SELL"
        abs_delta = abs(delta_value)

        if side == "SELL":
            # Sell: size by base-asset quantity; must round down to step_size.
            qty = _round_down(abs_delta / price, filt.step_size)
            notional = qty * price
            if qty <= 0 or notional < filt.min_notional:
                continue
        else:
            # Buy: size by quote-asset notional. Using quoteOrderQty lets
            # Binance deduct trading fees correctly and avoids insufficient-
            # funds errors that arise when a prior sell's fee reduces the
            # available quote balance below the planned notional.
            notional = abs_delta.quantize(_NOTIONAL_QUANT)
            if notional < filt.min_notional:
                continue
            qty = notional / price  # informational estimate; not sent to Binance

        trade = Trade(symbol=sym, pair=pair, side=side, quantity=qty, notional=notional)
        (buys if side == "BUY" else sells).append(trade)

    return sells + buys


def _pair(base: str, quote: str) -> str:
    return f"{base}{quote}"


def _round_down(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step
