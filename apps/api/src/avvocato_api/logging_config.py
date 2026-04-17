"""Configurazione structlog per log JSON pronti per Cloud Logging."""

from __future__ import annotations

import logging
import sys

import structlog

from avvocato_rag_core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.app_env == "local":
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        # JSON per Cloud Logging (usa "severity" invece di "level")
        processors.extend(
            [
                structlog.processors.EventRenamer("message"),
                _rename_level_to_severity,
                structlog.processors.JSONRenderer(),
            ]
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _rename_level_to_severity(_, __, event_dict: dict) -> dict:
    if "level" in event_dict:
        event_dict["severity"] = event_dict.pop("level").upper()
    return event_dict
