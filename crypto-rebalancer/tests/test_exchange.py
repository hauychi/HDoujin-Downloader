from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from rebalancer.exchange import BinanceExchange
from rebalancer.portfolio import Trade


@pytest.fixture
def ex(monkeypatch):
    # Patch the Client constructor so no network/auth happens.
    monkeypatch.setattr("rebalancer.exchange.Client", MagicMock())
    e = BinanceExchange("key", "secret", testnet=True)
    e.client = MagicMock()
    return e


def test_requires_credentials(monkeypatch):
    monkeypatch.setattr("rebalancer.exchange.Client", MagicMock())
    with pytest.raises(ValueError, match="not set"):
        BinanceExchange("", "", testnet=True)


def test_get_balances_filters_zero(ex):
    ex.client.get_account.return_value = {
        "balances": [
            {"asset": "BTC", "free": "1.5", "locked": "0"},
            {"asset": "ETH", "free": "0", "locked": "0"},
            {"asset": "USDT", "free": "1000", "locked": "0"},
        ]
    }
    result = ex.get_balances()
    assert result == {"BTC": Decimal("1.5"), "USDT": Decimal("1000")}


def test_get_prices_filters_and_parses(ex):
    ex.client.get_all_tickers.return_value = [
        {"symbol": "BTCUSDT", "price": "50000.1"},
        {"symbol": "ETHUSDT", "price": "3000.5"},
        {"symbol": "DOGEUSDT", "price": "0.08"},
    ]
    result = ex.get_prices(["BTCUSDT", "ETHUSDT"])
    assert result == {"BTCUSDT": Decimal("50000.1"), "ETHUSDT": Decimal("3000.5")}


def test_get_prices_raises_on_missing(ex):
    ex.client.get_all_tickers.return_value = [{"symbol": "BTCUSDT", "price": "50000"}]
    with pytest.raises(RuntimeError, match="missing tickers"):
        ex.get_prices(["BTCUSDT", "ETHUSDT"])


def test_get_symbol_filters_parses_filters(ex):
    ex.client.get_symbol_info.return_value = {
        "filters": [
            {"filterType": "LOT_SIZE", "stepSize": "0.00001"},
            {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
            {"filterType": "NOTIONAL", "minNotional": "10"},
        ]
    }
    f = ex.get_symbol_filters("BTCUSDT")
    assert f.step_size == Decimal("0.00001")
    assert f.tick_size == Decimal("0.01")
    assert f.min_notional == Decimal("10")


def test_place_market_order_buy_uses_quote_order_qty(ex):
    """Buys must use quoteOrderQty so Binance deducts fees from the quote side
    (otherwise a sell's fee would leave the buy underfunded)."""
    ex.client.order_market_buy.return_value = {"orderId": 1, "status": "FILLED"}
    trade = Trade(
        symbol="ETH", pair="ETHUSDT", side="BUY",
        quantity=Decimal("0.8"),  # informational estimate
        notional=Decimal("2000"),  # authoritative for buy
    )
    resp = ex.place_market_order(trade)
    ex.client.order_market_buy.assert_called_once_with(symbol="ETHUSDT", quoteOrderQty="2000")
    ex.client.order_market_sell.assert_not_called()
    assert resp["status"] == "FILLED"


def test_place_market_order_sell_uses_quantity(ex):
    ex.client.order_market_sell.return_value = {"orderId": 2, "status": "FILLED"}
    trade = Trade(
        symbol="ETH", pair="ETHUSDT", side="SELL",
        quantity=Decimal("0.5"), notional=Decimal("1250"),
    )
    ex.place_market_order(trade)
    ex.client.order_market_sell.assert_called_once_with(symbol="ETHUSDT", quantity="0.5")
    ex.client.order_market_buy.assert_not_called()


def test_place_market_order_rejects_bad_side(ex):
    bad = Trade(
        symbol="BTC", pair="BTCUSDT", side="HOLD",
        quantity=Decimal("1"), notional=Decimal("50000"),
    )
    with pytest.raises(ValueError, match="invalid side"):
        ex.place_market_order(bad)
