from __future__ import annotations

import logging
import os

from telegram_notifier import telegram_notifier


class AppLogger(logging.Logger):
    def success(self, msg: str, *args, **kwargs) -> None:
        self.info(msg, *args, **kwargs)


class TelegramLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        if not telegram_notifier.enabled:
            return
        try:
            message = self.format(record)
        except Exception:
            message = record.getMessage()
        telegram_notifier.send(message)


logging.setLoggerClass(AppLogger)

logger = logging.getLogger("unhedged")
if not logger.handlers:
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    telegram_level_name = os.getenv("TELEGRAM_LOG_LEVEL", "WARNING").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    if telegram_notifier.enabled:
        telegram_handler = TelegramLogHandler()
        telegram_handler.setLevel(getattr(logging, telegram_level_name, logging.WARNING))
        telegram_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(telegram_handler)
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    logger.propagate = False
