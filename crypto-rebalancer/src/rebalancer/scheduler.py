from __future__ import annotations

import logging
import signal
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import PortfolioConfig
from .exchange import BinanceExchange
from .rebalancer import tick

log = logging.getLogger(__name__)


def _tick_safely(cfg: PortfolioConfig, exchange: BinanceExchange, state_path: Path) -> None:
    """Run a tick but never propagate — scheduler must survive transient errors."""
    try:
        tick(cfg, exchange, state_path=state_path)
    except Exception:
        log.exception("tick failed; scheduler will retry on next interval")


def run_forever(cfg: PortfolioConfig, exchange: BinanceExchange, state_path: Path) -> None:
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        _tick_safely,
        trigger=IntervalTrigger(seconds=cfg.check_interval_seconds),
        kwargs={"cfg": cfg, "exchange": exchange, "state_path": state_path},
        id="rebalance-tick",
        coalesce=True,
        max_instances=1,
    )

    def _shutdown(signum, _frame):
        log.info("signal %s received, shutting down", signum)
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info(
        "scheduler started: interval=%ds dry_run=%s testnet=%s",
        cfg.check_interval_seconds,
        cfg.dry_run,
        cfg.use_testnet,
    )
    # Run one tick immediately so users get feedback without waiting an interval.
    _tick_safely(cfg, exchange, state_path)
    scheduler.start()
