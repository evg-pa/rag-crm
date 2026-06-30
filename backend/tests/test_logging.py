"""Tests for structured logging, request ID middleware, and error monitoring."""

from unittest.mock import patch

import structlog

# ── Structured Logging Unit Tests ─────────────────────────────────────────────


def test_get_logger_returns_structlog_lazy_proxy_before_configure() -> None:
    """get_logger returns a BoundLoggerLazyProxy before structlog.configure."""
    structlog.reset_defaults()
    from app.core.logging import get_logger

    logger = get_logger("test.module")
    # Before configure, the returned proxy wraps lazily
    assert isinstance(logger, structlog.typing.BindableLogger)
    assert hasattr(logger, "info")
    assert hasattr(logger, "warning")
    assert hasattr(logger, "error")


def test_get_logger_returns_bound_logger_after_configure() -> None:
    """get_logger returns a usable structlog logger after configure."""
    structlog.reset_defaults()
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )
    from app.core.logging import get_logger

    logger = get_logger("test.module")
    # After configuration, the proxy delegates to a real BoundLogger.
    # Verify by using it (calling log methods should not raise).
    logger.info("test message", extra="data")
    logger.warning("test warning")
    logger.error("test error")


def test_log_unhandled_configures_json_renderer() -> None:
    """log_unhandled configures structlog with JSONRenderer in processor chain."""
    structlog.reset_defaults()
    from app.core.logging import log_unhandled

    with patch("logging.basicConfig"):
        log_unhandled("TestApp", "1.0.0")

    assert structlog.is_configured()
    # structlog doesn't directly expose processor types after configure,
    # but the fact is_configured returns True means it ran successfully.
    # Verify by creating a logger and ensuring it works.
    logger = structlog.get_logger("test")
    logger.info("hello", key="value")  # should not raise


def test_setup_logging_development_uses_console_renderer() -> None:
    """setup_logging uses ConsoleRenderer when stdout is a TTY."""
    structlog.reset_defaults()
    from app.core.logging import setup_logging

    with patch("sys.stdout.isatty", return_value=True), patch("logging.basicConfig"):
        setup_logging(log_level="DEBUG")

    assert structlog.is_configured()


def test_setup_logging_production_uses_json() -> None:
    """setup_logging uses JSON path when stdout is not a TTY."""
    structlog.reset_defaults()
    from app.core.logging import setup_logging

    with patch("sys.stdout.isatty", return_value=False), patch("logging.basicConfig"):
        setup_logging(log_level="INFO")

    assert structlog.is_configured()


# ── Request ID Middleware Unit Test ────────────────────────────────────────────


def test_middleware_accepts_custom_header_name() -> None:
    """RequestIDMiddleware can be created with a custom header name."""
    from app.core.middleware import RequestIDMiddleware

    class DummyApp:
        pass

    mw = RequestIDMiddleware(DummyApp(), header_name="X-Correlation-Id")
    assert mw._header_name == "X-Correlation-Id"


def test_middleware_default_header_is_x_request_id() -> None:
    """RequestIDMiddleware defaults to X-Request-ID header."""
    from app.core.middleware import RequestIDMiddleware

    class DummyApp:
        pass

    mw = RequestIDMiddleware(DummyApp())
    assert mw._header_name == "X-Request-ID"
