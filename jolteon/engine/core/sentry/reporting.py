"""Optional, privacy-conscious reporting of terminal operational failures."""

import logging
import os
from typing import Any

import sentry_sdk
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.types import Event

from jolteon.engine.core.secrets import looks_secret


def configure(
    *, exchange: str, symbol: str, mode: str, component: str
) -> bool:
    """Enable Sentry when configured, returning whether it was enabled."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        release=os.environ.get("JOLTEON_RELEASE") or None,
        environment=os.environ.get("JOLTEON_ENVIRONMENT", "development"),
        send_default_pii=False,
        traces_sample_rate=0.0,
        profiles_sample_rate=0.0,
        shutdown_timeout=2,
        before_send=_before_send,
        integrations=[
            LoggingIntegration(level=logging.ERROR, event_level=None)
        ],
    )
    sentry_sdk.set_tags(
        {
            "exchange": exchange,
            "symbol": symbol.replace("-", "/"),
            "mode": mode,
            "component": component,
            "service": os.environ.get("JOLTEON_SERVICE", "local"),
        }
    )
    return True


def capture_operational_exception(
    error: BaseException, *, operation: str
) -> None:
    """Report a handled failure that prevents an exchange operation."""
    if not os.environ.get("SENTRY_DSN"):
        return
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("operation", operation)
        sentry_sdk.capture_exception(error)


def _before_send(event: Event, hint: dict[str, Any]) -> Event:
    """Remove request, user, local-variable, and secret-shaped event data."""
    del hint
    event.pop("request", None)
    event.pop("user", None)
    _scrub(event)
    return event


def _scrub(value: Any) -> None:
    if isinstance(value, dict):
        for key in list(value):
            if str(key).lower() == "vars" or looks_secret(str(key)):
                value.pop(key, None)
            else:
                _scrub(value[key])
    elif isinstance(value, list):
        for item in value:
            _scrub(item)
