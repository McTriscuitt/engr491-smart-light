"""Device token parsing and checking (DESIGN.md 6.3, 6.4, 8).

Tokens come from the DEVICE_TOKENS environment variable as comma-separated
`name:token` pairs. Tokens are never logged.
"""

import hmac


class ConfigError(Exception):
    """Raised when DEVICE_TOKENS is missing or malformed."""


def parse_device_tokens(raw):
    """Parse `name:token,name:token` into a list of (name, token) pairs.

    Raises ConfigError if nothing usable is configured. Error messages name the
    problem but never include a token value.
    """
    if not raw or not raw.strip():
        raise ConfigError("DEVICE_TOKENS is not set; at least one name:token pair is required")

    pairs = []
    names = set()
    for index, entry in enumerate(raw.split(","), start=1):
        entry = entry.strip()
        if not entry:
            continue
        name, sep, token = entry.partition(":")
        name, token = name.strip(), token.strip()
        if not sep or not name or not token:
            raise ConfigError(f"DEVICE_TOKENS entry {index} is not in name:token form")
        if name in names:
            raise ConfigError(f"DEVICE_TOKENS has a duplicate board name: {name}")
        names.add(name)
        pairs.append((name, token))

    if not pairs:
        raise ConfigError("DEVICE_TOKENS is not set; at least one name:token pair is required")
    return pairs


def bearer_token(header_value):
    """Return the token from an `Authorization: Bearer <token>` header, or None."""
    if not header_value:
        return None
    scheme, _, token = header_value.strip().partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def board_for_token(token, pairs):
    """Return the board name for `token`, or None.

    Every configured token is compared with hmac.compare_digest, with no early
    exit, so timing doesn't reveal which token (if any) was close.
    """
    if token is None:
        return None
    presented = token.encode("utf-8")
    match = None
    for name, expected in pairs:
        if hmac.compare_digest(presented, expected.encode("utf-8")):
            match = name
    return match
