from decimal import Decimal

from rebalancer.portfolio import (
    SymbolFilters,
    compute_drifts,
    compute_trades,
    compute_weights,
    needs_rebalance,
)


def _D(x):
    return Decimal(str(x))


def test_compute_weights_basic():
    balances = {"BTC": _D("1"), "ETH": _D("10"), "USDT": _D("1000")}
    prices = {"BTCUSDT": _D("50000"), "ETHUSDT": _D("3000")}
    total, weights = compute_weights(balances, prices, ["BTC", "ETH"], "USDT")
    assert total == _D("81000")
    assert weights["BTC"] == _D("50000") / _D("81000")
    assert weights["ETH"] == _D("30000") / _D("81000")
    assert weights["USDT"] == _D("1000") / _D("81000")


def test_compute_weights_ignores_untracked_assets():
    balances = {"BTC": _D("1"), "DOGE": _D("99999"), "USDT": _D("0")}
    prices = {"BTCUSDT": _D("50000")}
    total, weights = compute_weights(balances, prices, ["BTC"], "USDT")
    assert total == _D("50000")
    assert weights["BTC"] == _D("1")
    assert weights["USDT"] == _D("0")
    assert "DOGE" not in weights


def test_compute_weights_zero_portfolio():
    balances = {}
    prices = {"BTCUSDT": _D("50000")}
    total, weights = compute_weights(balances, prices, ["BTC"], "USDT")
    assert total == 0
    assert weights["BTC"] == 0


def test_compute_drifts():
    weights = {"BTC": _D("0.55"), "ETH": _D("0.25")}
    targets = {"BTC": 0.5, "ETH": 0.3}
    drifts = compute_drifts(weights, targets)
    assert drifts["BTC"] == _D("0.05")
    assert drifts["ETH"] == _D("-0.05")


def test_needs_rebalance_threshold_boundary():
    drifts = {"BTC": _D("0.05"), "ETH": _D("-0.03")}
    assert needs_rebalance(drifts, 0.05) is True
    assert needs_rebalance(drifts, 0.06) is False


def test_compute_trades_buys_and_sells():
    targets = {"BTC": 0.5, "ETH": 0.5}
    # Current: BTC overweight, ETH underweight.
    weights = {"BTC": _D("0.7"), "ETH": _D("0.3"), "USDT": _D("0")}
    prices = {"BTCUSDT": _D("50000"), "ETHUSDT": _D("2500")}
    filters = {
        "BTCUSDT": SymbolFilters(_D("0.00001"), _D("0.01"), _D("10")),
        "ETHUSDT": SymbolFilters(_D("0.0001"), _D("0.01"), _D("10")),
    }
    trades = compute_trades(
        total_value=_D("10000"),
        weights=weights,
        targets=targets,
        prices=prices,
        filters=filters,
        quote="USDT",
        max_trade_quote=10_000,
    )
    sides = [t.side for t in trades]
    assert sides == ["SELL", "BUY"]  # sells first
    sell, buy = trades
    assert sell.pair == "BTCUSDT"
    assert buy.pair == "ETHUSDT"
    # BTC current value 7000, target 5000 -> sell 2000 / 50000 = 0.04
    assert sell.quantity == _D("0.04")
    # ETH current value 3000, target 5000 -> buy 2000 / 2500 = 0.8
    assert buy.quantity == _D("0.8")


def test_compute_trades_respects_max_trade_cap():
    targets = {"BTC": 0.5, "ETH": 0.5}
    weights = {"BTC": _D("0.9"), "ETH": _D("0.1"), "USDT": _D("0")}
    prices = {"BTCUSDT": _D("50000"), "ETHUSDT": _D("2500")}
    filters = {
        "BTCUSDT": SymbolFilters(_D("0.00001"), _D("0.01"), _D("10")),
        "ETHUSDT": SymbolFilters(_D("0.0001"), _D("0.01"), _D("10")),
    }
    trades = compute_trades(
        total_value=_D("10000"),
        weights=weights,
        targets=targets,
        prices=prices,
        filters=filters,
        quote="USDT",
        max_trade_quote=100,  # hard cap
    )
    # Each leg capped at 100 USDT notional.
    assert all(t.notional <= _D("100") for t in trades)


def test_compute_trades_skips_below_min_notional():
    targets = {"BTC": 0.5, "ETH": 0.5}
    weights = {"BTC": _D("0.51"), "ETH": _D("0.49"), "USDT": _D("0")}  # tiny drift
    prices = {"BTCUSDT": _D("50000"), "ETHUSDT": _D("2500")}
    filters = {
        "BTCUSDT": SymbolFilters(_D("0.00001"), _D("0.01"), _D("1000")),  # absurdly high
        "ETHUSDT": SymbolFilters(_D("0.0001"), _D("0.01"), _D("1000")),
    }
    trades = compute_trades(
        total_value=_D("10000"),
        weights=weights,
        targets=targets,
        prices=prices,
        filters=filters,
        quote="USDT",
        max_trade_quote=10_000,
    )
    assert trades == []  # both legs would be ~100 USDT notional, below 1000


def test_compute_trades_rounds_down_to_step_size():
    targets = {"BTC": 1.0}  # invalid in config but fine for unit math
    weights = {"BTC": _D("0.5"), "USDT": _D("0.5")}
    prices = {"BTCUSDT": _D("30000")}
    filters = {"BTCUSDT": SymbolFilters(_D("0.001"), _D("0.01"), _D("10"))}
    trades = compute_trades(
        total_value=_D("10000"),
        weights=weights,
        targets=targets,
        prices=prices,
        filters=filters,
        quote="USDT",
        max_trade_quote=10_000,
    )
    assert len(trades) == 1
    # target 10000 USDT in BTC, currently 5000 -> buy 5000/30000 = 0.16666..., rounded down to 0.166
    assert trades[0].quantity == _D("0.166")
