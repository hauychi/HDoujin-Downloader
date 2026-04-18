from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import load_config
from .exchange import BinanceExchange
from .logging_conf import setup_logging
from .rebalancer import tick
from .scheduler import run_forever

app = typer.Typer(add_completion=False, help="Binance Spot portfolio rebalancer.")
console = Console()

_CFG_OPT = typer.Option(
    Path("portfolio.yaml"),
    "--config",
    "-c",
    exists=True,
    dir_okay=False,
    readable=True,
    help="Path to portfolio.yaml.",
)
_LOG_OPT = typer.Option("INFO", "--log-level", "-l", help="DEBUG/INFO/WARNING/ERROR.")


def _build(cfg_path: Path, log_level: str):
    setup_logging(log_level)
    cfg = load_config(cfg_path)
    exchange = BinanceExchange(
        api_key=cfg.api_key or "",
        api_secret=cfg.api_secret or "",
        testnet=cfg.use_testnet,
    )
    return cfg, exchange


@app.command()
def run(config: Path = _CFG_OPT, log_level: str = _LOG_OPT) -> None:
    """Start the long-running scheduler loop."""
    cfg, exchange = _build(config, log_level)
    run_forever(cfg, exchange)


@app.command()
def check(config: Path = _CFG_OPT, log_level: str = _LOG_OPT) -> None:
    """Run a single tick in forced dry-run mode. Never places orders."""
    cfg, exchange = _build(config, log_level)
    tick(cfg, exchange, force_dry_run=True)


@app.command()
def balances(config: Path = _CFG_OPT, log_level: str = _LOG_OPT) -> None:
    """Print free balances and their quote-currency value."""
    cfg, exchange = _build(config, log_level)
    bals = exchange.get_balances()
    pairs = [f"{s}{cfg.quote}" for s in cfg.asset_symbols]
    prices = exchange.get_prices(pairs) if pairs else {}

    table = Table(title=f"Balances ({'testnet' if cfg.use_testnet else 'mainnet'})")
    table.add_column("asset")
    table.add_column("free", justify="right")
    table.add_column(f"value ({cfg.quote})", justify="right")
    total = Decimal(0)
    for asset, qty in sorted(bals.items()):
        if asset == cfg.quote:
            value = qty
        else:
            px = prices.get(f"{asset}{cfg.quote}")
            value = qty * px if px else Decimal(0)
        total += value
        table.add_row(asset, f"{qty}", f"{value:.2f}")
    table.add_section()
    table.add_row("TOTAL", "", f"{total:.2f}")
    console.print(table)


if __name__ == "__main__":
    app()
