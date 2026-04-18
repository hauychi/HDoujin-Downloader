"""Thin wrapper around python-binance."""
from __future__ import annotations

import logging
from decimal import Decimal

from binance.client import Client
from binance.exceptions import BinanceAPIException
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .portfolio import SymbolFilters, Trade

log = logging.getLogger(__name__)

_RETRY = dict(
    retry=retry_if_exception_type(BinanceAPIException),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    reraise=True,
)


class BinanceExchange:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        if not api_key or not api_secret:
            raise ValueError("BINANCE_API_KEY / BINANCE_API_SECRET not set")
        self.client = Client(api_key, api_secret, testnet=testnet)
        self.testnet = testnet
        self._filter_cache: dict[str, SymbolFilters] = {}

    @retry(**_RETRY)
    def get_balances(self) -> dict[str, Decimal]:
        """Return {asset: free_balance} for non-zero free balances."""
        account = self.client.get_account()
        out: dict[str, Decimal] = {}
        for bal in account["balances"]:
            free = Decimal(bal["free"])
            if free > 0:
                out[bal["asset"]] = free
        return out

    @retry(**_RETRY)
    def get_prices(self, pairs: list[str]) -> dict[str, Decimal]:
        """Return {pair: last_price} for the requested pairs."""
        wanted = set(pairs)
        tickers = self.client.get_all_tickers()
        out: dict[str, Decimal] = {}
        for t in tickers:
            if t["symbol"] in wanted:
                out[t["symbol"]] = Decimal(t["price"])
        missing = wanted - out.keys()
        if missing:
            raise RuntimeError(f"missing tickers from Binance: {sorted(missing)}")
        return out

    def get_symbol_filters(self, pair: str) -> SymbolFilters:
        if pair in self._filter_cache:
            return self._filter_cache[pair]
        info = self.client.get_symbol_info(pair)
        if info is None:
            raise RuntimeError(f"unknown Binance symbol {pair}")
        step = tick = min_notional = None
        for f in info["filters"]:
            ftype = f["filterType"]
            if ftype == "LOT_SIZE":
                step = Decimal(f["stepSize"])
            elif ftype == "PRICE_FILTER":
                tick = Decimal(f["tickSize"])
            elif ftype in ("MIN_NOTIONAL", "NOTIONAL"):
                # MIN_NOTIONAL on older symbols; NOTIONAL on newer symbols.
                raw = f.get("minNotional") or f.get("notional") or "0"
                min_notional = Decimal(raw)
        if step is None or tick is None or min_notional is None:
            raise RuntimeError(f"incomplete symbol filters for {pair}: {info['filters']}")
        result = SymbolFilters(step_size=step, tick_size=tick, min_notional=min_notional)
        self._filter_cache[pair] = result
        return result

    @retry(**_RETRY)
    def place_market_order(self, trade: Trade) -> dict:
        """Place a market order.

        SELL orders size by base-asset quantity (rounded to step_size).
        BUY orders size by quoteOrderQty so Binance deducts the trading fee
        from the quote balance we actually have — otherwise buy-after-sell
        would fail because the 0.1% sell fee reduces available quote.
        """
        side = trade.side.upper()
        if side == "SELL":
            qty_str = _format_decimal(trade.quantity)
            log.info("placing SELL %s quantity=%s (testnet=%s)", trade.pair, qty_str, self.testnet)
            return self.client.order_market_sell(symbol=trade.pair, quantity=qty_str)
        if side == "BUY":
            notional_str = _format_decimal(trade.notional)
            log.info(
                "placing BUY %s quoteOrderQty=%s (testnet=%s)",
                trade.pair,
                notional_str,
                self.testnet,
            )
            return self.client.order_market_buy(symbol=trade.pair, quoteOrderQty=notional_str)
        raise ValueError(f"invalid side {side!r}")


def _format_decimal(d: Decimal) -> str:
    """Render a Decimal in fixed-point form. `normalize()` strips trailing
    zeros; the `f` format spec avoids scientific notation (e.g. 1E+1 -> 10)."""
    return format(d.normalize(), "f")
