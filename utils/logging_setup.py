"""Shared logging configuration for the whole platform."""

import logging

from config.settings import LOG_LEVEL


def configure_logging() -> None:
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
