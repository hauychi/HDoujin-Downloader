"""Integration-ish tests for rebalancer.tick()."""
from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from rebalancer import rebalancer
from rebalancer.config import PortfolioConfig
from rebalancer.portfolio import SymbolFilters


def _cfg(**overrides) -> PortfolioConfig:
    base = dict(
        assets=[{"symbol": "BTC", "weight": 0.5}, {"symbol": "ETH", "weight": 0.5}],
        quote="USDT",
        drift_threshold=0.05,
        check_interval_seconds=900,
        min_rebalance_interval_seconds=3600,
        max_trade_usdt=10_000.0,
        dry_run=False,
        use_testnet=True,
    )
    base.update(overrides)
    return PortfolioConfig.model_validate(base)


def _mock_exchange(balances, prices, filters):
    mock = MagicMock()
    mock.get_balances.return_value = balances
    mock.get_prices.return_value = prices
    mock.get_symbol_filters.side_effect = lambda pair: filters[pair]
    return mock


def test_tick_writes_state_to_given_path(tmp_path: Path):
    cfg = _cfg()
    state_path = tmp_path / "state.json"
    ex = _mock_exchange(
        balances={"BTC": Decimal("0.14"), "ETH": Decimal("1.0"), "USDT": Decimal("0")},
        prices={"BTCUSDT": Decimal("50000"), "ETHUSDT": Decimal("2500")},
        filters={
            "BTCUSDT": SymbolFilters(Decimal("0.00001"), Decimal("0.01"), Decimal("10")),
            "ETHUSDT": SymbolFilters(Decimal("0.0001"), Decimal("0.01"), Decimal("10")),
        },
    )
    ex.place_market_order.return_value = {"orderId": 1, "status": "FILLED"}

    rebalancer.tick(cfg, ex, state_path=state_path)

    # Orders placed, state written to the supplied path.
    assert ex.place_market_order.called
    assert state_path.exists()
    state = json.loads(state_path.read_text())
    assert "last_rebalance_ts" in state


def test_tick_respects_cooldown(tmp_path: Path):
    cfg = _cfg()
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"last_rebalance_ts": time.time()}))  # fresh rebalance

    ex = _mock_exchange(
        balances={"BTC": Decimal("0.14"), "ETH": Decimal("1.0"), "USDT": Decimal("0")},
        prices={"BTCUSDT": Decimal("50000"), "ETHUSDT": Decimal("2500")},
        filters={},  # won't be consulted
    )

    rebalancer.tick(cfg, ex, state_path=state_path)

    # Cooldown active → no orders placed.
    ex.place_market_order.assert_not_called()


def test_tick_aborts_on_first_order_failure(tmp_path: Path):
    """If a sell fails, subsequent buys would almost certainly fail too
    (insufficient quote). The loop must bail out, not cascade errors."""
    cfg = _cfg()
    state_path = tmp_path / "state.json"

    ex = _mock_exchange(
        balances={"BTC": Decimal("0.14"), "ETH": Decimal("1.0"), "USDT": Decimal("0")},
        prices={"BTCUSDT": Decimal("50000"), "ETHUSDT": Decimal("2500")},
        filters={
            "BTCUSDT": SymbolFilters(Decimal("0.00001"), Decimal("0.01"), Decimal("10")),
            "ETHUSDT": SymbolFilters(Decimal("0.0001"), Decimal("0.01"), Decimal("10")),
        },
    )
    ex.place_market_order.side_effect = RuntimeError("first order blew up")

    rebalancer.tick(cfg, ex, state_path=state_path)

    # Two trades were planned (SELL BTC, BUY ETH), but only the first runs
    # before the loop aborts.
    assert ex.place_market_order.call_count == 1


def test_tick_force_dry_run_never_places_orders(tmp_path: Path):
    cfg = _cfg(dry_run=False)  # live mode in config…
    state_path = tmp_path / "state.json"
    ex = _mock_exchange(
        balances={"BTC": Decimal("0.14"), "ETH": Decimal("1.0"), "USDT": Decimal("0")},
        prices={"BTCUSDT": Decimal("50000"), "ETHUSDT": Decimal("2500")},
        filters={
            "BTCUSDT": SymbolFilters(Decimal("0.00001"), Decimal("0.01"), Decimal("10")),
            "ETHUSDT": SymbolFilters(Decimal("0.0001"), Decimal("0.01"), Decimal("10")),
        },
    )

    # …but force_dry_run=True must override.
    rebalancer.tick(cfg, ex, state_path=state_path, force_dry_run=True)

    ex.place_market_order.assert_not_called()
    assert not state_path.exists()  # state not written in dry-run mode
