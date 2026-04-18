from pathlib import Path

import pytest
import yaml

from rebalancer.config import PortfolioConfig, load_config


def _base_cfg(**overrides):
    cfg = dict(
        assets=[{"symbol": "BTC", "weight": 0.6}, {"symbol": "ETH", "weight": 0.4}],
        quote="USDT",
        drift_threshold=0.05,
        check_interval_seconds=900,
        min_rebalance_interval_seconds=3600,
        max_trade_usdt=500.0,
        dry_run=True,
        use_testnet=True,
    )
    cfg.update(overrides)
    return cfg


def test_valid_config():
    cfg = PortfolioConfig.model_validate(_base_cfg())
    assert cfg.asset_symbols == ["BTC", "ETH"]
    assert cfg.targets == {"BTC": 0.6, "ETH": 0.4}


def test_weights_must_sum_to_one():
    with pytest.raises(ValueError, match="sum to 1"):
        PortfolioConfig.model_validate(
            _base_cfg(assets=[{"symbol": "BTC", "weight": 0.6}, {"symbol": "ETH", "weight": 0.3}])
        )


def test_duplicate_symbols_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        PortfolioConfig.model_validate(
            _base_cfg(assets=[{"symbol": "BTC", "weight": 0.5}, {"symbol": "btc", "weight": 0.5}])
        )


def test_quote_cannot_be_an_asset():
    with pytest.raises(ValueError, match="quote"):
        PortfolioConfig.model_validate(
            _base_cfg(
                quote="BTC",
                assets=[{"symbol": "BTC", "weight": 0.5}, {"symbol": "ETH", "weight": 0.5}],
            )
        )


def test_threshold_range():
    with pytest.raises(ValueError):
        PortfolioConfig.model_validate(_base_cfg(drift_threshold=0))
    with pytest.raises(ValueError):
        PortfolioConfig.model_validate(_base_cfg(drift_threshold=1))


def test_symbol_uppercased():
    cfg = PortfolioConfig.model_validate(
        _base_cfg(assets=[{"symbol": "btc", "weight": 0.5}, {"symbol": "eth", "weight": 0.5}])
    )
    assert cfg.asset_symbols == ["BTC", "ETH"]


def test_load_config_from_yaml(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "k")
    monkeypatch.setenv("BINANCE_API_SECRET", "s")
    p = tmp_path / "portfolio.yaml"
    p.write_text(yaml.safe_dump(_base_cfg()))
    cfg = load_config(p)
    assert cfg.api_key == "k"
    assert cfg.api_secret == "s"
    assert cfg.quote == "USDT"
