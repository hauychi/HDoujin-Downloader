from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from .config import load_config
from .exchange import BinanceExchange
from .logging_conf import setup_logging
from .rebalancer import DEFAULT_STATE_FILENAME, tick
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
_FMT_OPT = typer.Option(
    "rich", "--log-format", "-f", help="Log output format: 'rich' (human) or 'json'."
)


def _build(cfg_path: Path, log_level: str, log_format: str = "rich"):
    setup_logging(log_level, log_format)
    cfg = load_config(cfg_path)
    exchange = BinanceExchange(
        api_key=cfg.api_key or "",
        api_secret=cfg.api_secret or "",
        testnet=cfg.use_testnet,
    )
    state_path = cfg_path.parent / DEFAULT_STATE_FILENAME
    return cfg, exchange, state_path


@app.command()
def run(
    config: Path = _CFG_OPT,
    log_level: str = _LOG_OPT,
    log_format: str = _FMT_OPT,
) -> None:
    """Start the long-running scheduler loop."""
    cfg, exchange, state_path = _build(config, log_level, log_format)
    run_forever(cfg, exchange, state_path)


@app.command()
def check(
    config: Path = _CFG_OPT,
    log_level: str = _LOG_OPT,
    log_format: str = _FMT_OPT,
) -> None:
    """Run a single tick in forced dry-run mode. Never places orders."""
    cfg, exchange, state_path = _build(config, log_level, log_format)
    tick(cfg, exchange, state_path=state_path, force_dry_run=True)


@app.command()
def balances(
    config: Path = _CFG_OPT,
    log_level: str = _LOG_OPT,
    log_format: str = _FMT_OPT,
) -> None:
    """Print free balances and their quote-currency value."""
    cfg, exchange, _ = _build(config, log_level, log_format)
    bals = exchange.get_balances()

    # Price every non-quote balance, not just the configured targets. Any
    # coin without a direct pair against the quote shows as unpriced.
    priceable = sorted({asset for asset in bals if asset != cfg.quote})
    pairs = [f"{a}{cfg.quote}" for a in priceable]
    prices: dict[str, Decimal] = {}
    if pairs:
        try:
            prices = exchange.get_prices(pairs)
        except RuntimeError:
            # Some held coins may not have a direct {coin}{quote} pair.
            # Fall back to fetching each one individually.
            for pair in pairs:
                try:
                    prices.update(exchange.get_prices([pair]))
                except RuntimeError:
                    pass  # leave unpriced

    table = Table(title=f"Balances ({'testnet' if cfg.use_testnet else 'mainnet'})")
    table.add_column("asset")
    table.add_column("free", justify="right")
    table.add_column(f"value ({cfg.quote})", justify="right")
    total = Decimal(0)
    for asset, qty in sorted(bals.items()):
        if asset == cfg.quote:
            value = qty
            total += value
            table.add_row(asset, f"{qty}", f"{value:.2f}")
            continue
        px = prices.get(f"{asset}{cfg.quote}")
        if px is None:
            table.add_row(asset, f"{qty}", "-")
            continue
        value = qty * px
        total += value
        table.add_row(asset, f"{qty}", f"{value:.2f}")
    table.add_section()
    table.add_row("TOTAL", "", f"{total:.2f}")
    console.print(table)


if __name__ == "__main__":
    app()
