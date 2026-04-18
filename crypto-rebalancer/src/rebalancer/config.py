from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

WEIGHT_TOLERANCE = 1e-6


class AssetTarget(BaseModel):
    symbol: str
    weight: float = Field(gt=0, lt=1)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        v = v.strip().upper()
        if not v.isalnum():
            raise ValueError(f"symbol must be alphanumeric, got {v!r}")
        return v


class PortfolioConfig(BaseModel):
    assets: list[AssetTarget]
    quote: str = "USDT"
    drift_threshold: float = Field(gt=0, lt=1)
    check_interval_seconds: int = Field(ge=10)
    min_rebalance_interval_seconds: int = Field(ge=0)
    max_trade_usdt: float = Field(gt=0)
    dry_run: bool = True
    use_testnet: bool = True

    api_key: str | None = None
    api_secret: str | None = None

    @field_validator("quote")
    @classmethod
    def _quote_upper(cls, v: str) -> str:
        return v.strip().upper()

    @model_validator(mode="after")
    def _check_assets(self) -> PortfolioConfig:
        if not self.assets:
            raise ValueError("at least one asset is required")

        symbols = [a.symbol for a in self.assets]
        if len(set(symbols)) != len(symbols):
            raise ValueError(f"duplicate symbols in assets: {symbols}")

        if self.quote in symbols:
            raise ValueError(f"quote {self.quote!r} must not appear in assets list")

        total = sum(a.weight for a in self.assets)
        if abs(total - 1.0) > WEIGHT_TOLERANCE:
            raise ValueError(f"asset weights must sum to 1.0, got {total}")

        return self

    @property
    def asset_symbols(self) -> list[str]:
        return [a.symbol for a in self.assets]

    @property
    def targets(self) -> dict[str, float]:
        return {a.symbol: a.weight for a in self.assets}


def load_config(path: str | Path) -> PortfolioConfig:
    """Load YAML config and overlay API credentials from environment."""
    load_dotenv()

    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    raw["api_key"] = os.getenv("BINANCE_API_KEY") or None
    raw["api_secret"] = os.getenv("BINANCE_API_SECRET") or None

    return PortfolioConfig.model_validate(raw)
