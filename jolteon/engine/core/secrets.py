"""Which names look like they hold a credential."""

SECRET_MARKERS = (
    "authorization",
    "cookie",
    "credential",
    "dsn",
    "key",
    "password",
    "secret",
    "signature",
    "token",
)


def looks_secret(name: str) -> bool:
    """
    Returns: Whether a field or key of this name might hold a credential.

    Judged on the name and not the value, because a value is only known
    once there is one - and anything recorded or reported by mistake
    cannot be taken back afterwards.
    """
    lowered = name.lower()
    return any(marker in lowered for marker in SECRET_MARKERS)
