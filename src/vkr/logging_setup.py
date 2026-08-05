from __future__ import annotations

import logging

from . import ui

LOGGER_NAME = "vkr"

_configured = False
_source_location = ""
_source_suppressions: tuple[str, ...] = ()


def set_source_location(location: str = "", suppress=()) -> None:
    global _source_location, _source_suppressions
    _source_location = location or ""
    _source_suppressions = tuple(suppress or ())


def source_location() -> str:
    return _source_location


def source_suppressions() -> tuple[str, ...]:
    return _source_suppressions


class _UIHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)
        console = ui.console()
        source = record.name.rsplit(".", 1)[-1]
        where = getattr(record, "location", "") or _source_location
        if record.levelno >= logging.WARNING:
            from . import suppress

            rule = getattr(record, "rule", "") or ""
            hit = suppress.matching(_source_suppressions, message, rule)
            if hit is not None:
                suppress.mark_used(hit, where)
            console.finding(
                ui.Finding(
                    severity="error" if record.levelno >= logging.ERROR else "warning",
                    message=message,
                    location=where,
                    source=source,
                    rule=rule,
                    suppressed=hit is not None,
                )
            )
        elif record.levelno >= logging.INFO:
            console.note(message)
        else:
            source = record.name.split(".", 1)[-1] if "." in record.name else ""
            console.debug(message, source)
        if record.exc_info and console.verbosity >= ui.DEBUG:
            import traceback

            for line in traceback.format_exception(*record.exc_info):
                for chunk in line.rstrip().splitlines():
                    console.debug(chunk)


def setup_logging(verbosity: int = ui.NORMAL) -> logging.Logger:
    global _configured

    level = {
        ui.QUIET: logging.WARNING,
        ui.NORMAL: logging.WARNING,
        ui.VERBOSE: logging.INFO,
        ui.DEBUG: logging.DEBUG,
    }.get(verbosity, logging.WARNING)

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    handler = _UIHandler()
    handler.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False
    _configured = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    base = logging.getLogger(LOGGER_NAME)
    if not _configured and not base.handlers:
        setup_logging()
    return base.getChild(name) if name else base
