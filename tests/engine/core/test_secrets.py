import pytest

from jolteon.engine.core.secrets import looks_secret


@pytest.mark.parametrize(
    "name",
    [
        "api_key",
        "KRAKEN_API_SECRET",
        "Authorization",
        "password",
        "session_token",
        "signature",
        "credentials",
        "cookie",
        "SENTRY_DSN",
    ],
)
def test_a_name_that_might_hold_a_credential_is_flagged(name):
    assert looks_secret(name)


@pytest.mark.parametrize(
    "name",
    [
        "quote_offset_in_bps",
        "maker_rate",
        "interval_in_seconds",
        "max_inventory",
    ],
)
def test_an_ordinary_tunable_is_not_flagged(name):
    assert not looks_secret(name)
