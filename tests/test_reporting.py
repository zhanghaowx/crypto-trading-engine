from unittest.mock import patch

from jolteon.engine.core.sentry import reporting


def test_an_unset_dsn_initializes_nothing(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)

    with patch("jolteon.engine.core.sentry.reporting.sentry_sdk.init") as init:
        assert not reporting.configure(
            exchange="Kraken",
            symbol="BTC-USD",
            mode="paper",
            component="engine",
        )

    init.assert_not_called()


def test_configured_reporting_has_identity_and_no_tracing(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv("JOLTEON_RELEASE", "abc123")
    monkeypatch.setenv("JOLTEON_SERVICE", "engine-kraken-btc-usd")

    with (
        patch("jolteon.engine.core.sentry.reporting.sentry_sdk.init") as init,
        patch(
            "jolteon.engine.core.sentry.reporting.sentry_sdk.set_tags"
        ) as set_tags,
    ):
        assert reporting.configure(
            exchange="Kraken",
            symbol="BTC-USD",
            mode="paper",
            component="engine",
        )

    options = init.call_args.kwargs
    assert options["send_default_pii"] is False
    assert options["traces_sample_rate"] == 0.0
    assert options["profiles_sample_rate"] == 0.0
    assert options["release"] == "abc123"
    set_tags.assert_called_once_with(
        {
            "exchange": "Kraken",
            "symbol": "BTC/USD",
            "mode": "paper",
            "component": "engine",
            "service": "engine-kraken-btc-usd",
        }
    )


def test_event_filter_removes_requests_locals_and_secrets():
    event = {
        "request": {"headers": {"Authorization": "secret"}},
        "user": {"email": "trader@example.com"},
        "extra": {
            "api_key": "key",
            "safe": "kept",
            "nested": {"signature": "signed", "count": 2},
        },
        "exception": {
            "values": [{"stacktrace": {"frames": [{"vars": {"x": 1}}]}}]
        },
    }

    filtered = reporting._before_send(event, {})

    assert "request" not in filtered
    assert "user" not in filtered
    assert filtered["extra"] == {"safe": "kept", "nested": {"count": 2}}
    frame = filtered["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert "vars" not in frame


def test_handled_operational_failure_is_tagged(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "configured")
    error = RuntimeError("order failed")

    with (
        patch(
            "jolteon.engine.core.sentry.reporting.sentry_sdk.new_scope"
        ) as new_scope,
        patch(
            "jolteon.engine.core.sentry.reporting.sentry_sdk.capture_exception"
        ) as capture,
    ):
        reporting.capture_operational_exception(
            error, operation="submit_order"
        )

    scope = new_scope.return_value.__enter__.return_value
    scope.set_tag.assert_called_once_with("operation", "submit_order")
    capture.assert_called_once_with(error)
