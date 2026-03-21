from __future__ import annotations

import logging
import os


class AppLogger(logging.Logger):
    def success(self, msg: str, *args, **kwargs) -> None:
        self.info(msg, *args, **kwargs)


logging.setLoggerClass(AppLogger)

logger = logging.getLogger("unhedged")
if not logger.handlers:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    logger.propagate = False
