from __future__ import annotations

import logging
import signal

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import PortfolioConfig
from .exchange import BinanceExchange
from .rebalancer import tick

log = logging.getLogger(__name__)


def run_forever(cfg: PortfolioConfig, exchange: BinanceExchange) -> None:
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        tick,
        trigger=IntervalTrigger(seconds=cfg.check_interval_seconds),
        args=(cfg, exchange),
        next_run_time=None,  # scheduler kicks first tick after the interval
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
    tick(cfg, exchange)
    scheduler.start()
