"""Orchestration: one rebalance tick."""
from __future__ import annotations

import json
import logging
import time
from decimal import Decimal
from pathlib import Path

from rich.console import Console
from rich.table import Table

from . import portfolio
from .config import PortfolioConfig
from .exchange import BinanceExchange

log = logging.getLogger(__name__)
console = Console()

STATE_FILE = Path("rebalancer_state.json")


def _load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read %s: %s", STATE_FILE, exc)
        return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except OSError as exc:
        log.warning("could not write %s: %s", STATE_FILE, exc)


def _print_drift_table(
    weights: dict[str, Decimal],
    targets: dict[str, float],
    drifts: dict[str, Decimal],
    total_value: Decimal,
    quote: str,
) -> None:
    table = Table(title=f"Portfolio ({total_value:.2f} {quote})")
    table.add_column("asset")
    table.add_column("weight", justify="right")
    table.add_column("target", justify="right")
    table.add_column("drift", justify="right")
    for sym, target in targets.items():
        w = weights.get(sym, Decimal(0))
        d = drifts[sym]
        table.add_row(sym, f"{w:.4f}", f"{target:.4f}", f"{d:+.4f}")
    w_quote = weights.get(quote, Decimal(0))
    table.add_row(quote, f"{w_quote:.4f}", "-", "-")
    console.print(table)


def tick(
    cfg: PortfolioConfig,
    exchange: BinanceExchange,
    force_dry_run: bool = False,
) -> None:
    """Run a single drift check and rebalance if needed."""
    dry_run = cfg.dry_run or force_dry_run

    balances = exchange.get_balances()
    pairs = [f"{s}{cfg.quote}" for s in cfg.asset_symbols]
    prices = exchange.get_prices(pairs)

    total_value, weights = portfolio.compute_weights(
        balances, prices, cfg.asset_symbols, cfg.quote
    )
    drifts = portfolio.compute_drifts(weights, cfg.targets)
    _print_drift_table(weights, cfg.targets, drifts, total_value, cfg.quote)

    if total_value <= 0:
        log.warning("portfolio total value is zero; nothing to rebalance")
        return

    if not portfolio.needs_rebalance(drifts, cfg.drift_threshold):
        log.info("no drift >= %.2f%%; skipping", cfg.drift_threshold * 100)
        return

    state = _load_state()
    last = state.get("last_rebalance_ts", 0)
    gap = time.time() - last
    if gap < cfg.min_rebalance_interval_seconds:
        log.info(
            "rebalance needed but last was %.0fs ago (< %ds min gap); skipping",
            gap,
            cfg.min_rebalance_interval_seconds,
        )
        return

    filters = {pair: exchange.get_symbol_filters(pair) for pair in pairs}
    trades = portfolio.compute_trades(
        total_value=total_value,
        weights=weights,
        targets=cfg.targets,
        prices=prices,
        filters=filters,
        quote=cfg.quote,
        max_trade_quote=cfg.max_trade_usdt,
    )

    if not trades:
        log.info("rebalance triggered but no trades pass min_notional/step_size filters")
        return

    log.info("%d trade(s) planned (dry_run=%s)", len(trades), dry_run)
    for t in trades:
        log.info("  %s %s qty=%s notional=%.2f %s", t.side, t.pair, t.quantity, t.notional, cfg.quote)
        if dry_run:
            continue
        try:
            resp = exchange.place_market_order(t.pair, t.side, t.quantity)
            log.info("    filled: orderId=%s status=%s", resp.get("orderId"), resp.get("status"))
        except Exception as exc:
            log.exception("    order FAILED for %s: %s", t.pair, exc)

    if not dry_run:
        state["last_rebalance_ts"] = time.time()
        _save_state(state)
