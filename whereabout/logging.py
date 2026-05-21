"""Structured logging setup. JSON to stderr when not a TTY; pretty to stdout when TTY."""
from __future__ import annotations
import sys
import structlog


def configure_logging(debug: bool = False) -> None:
    """Call once at CLI startup."""
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if sys.stderr.isatty():
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            10 if debug else 20  # DEBUG=10, INFO=20
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "whereabout"):
    return structlog.get_logger(name)
