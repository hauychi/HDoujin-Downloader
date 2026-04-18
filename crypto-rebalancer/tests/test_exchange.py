from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from rebalancer.exchange import BinanceExchange


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


def test_place_market_order_dispatches_buy(ex):
    ex.client.order_market_buy.return_value = {"orderId": 1, "status": "FILLED"}
    resp = ex.place_market_order("BTCUSDT", "BUY", Decimal("0.01"))
    ex.client.order_market_buy.assert_called_once_with(symbol="BTCUSDT", quantity="0.01")
    assert resp["status"] == "FILLED"


def test_place_market_order_dispatches_sell(ex):
    ex.client.order_market_sell.return_value = {"orderId": 2, "status": "FILLED"}
    ex.place_market_order("ETHUSDT", "SELL", Decimal("0.5"))
    ex.client.order_market_sell.assert_called_once_with(symbol="ETHUSDT", quantity="0.5")


def test_place_market_order_rejects_bad_side(ex):
    with pytest.raises(ValueError, match="invalid side"):
        ex.place_market_order("BTCUSDT", "HOLD", Decimal("1"))
