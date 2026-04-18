from __future__ import annotations

import logging

from rich.logging import RichHandler


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[RichHandler(rich_tracebacks=True, markup=False, show_path=False)],
    )
    # Binance client is chatty at DEBUG; keep it at WARNING.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
