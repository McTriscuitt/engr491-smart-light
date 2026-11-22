import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVER_DIR))

# Test-only tokens (not real). Set before `app` is imported, because app.py
# builds the module-level app at import time.
TRISTAN_TOKEN = "t" * 64
ALEX_TOKEN = "a" * 64
TEST_TOKENS = f"tristan:{TRISTAN_TOKEN},alex:{ALEX_TOKEN}"
os.environ.setdefault("DEVICE_TOKENS", TEST_TOKENS)


class FakeClock:
    """Injectable clock so timing tests advance time instead of sleeping."""

    def __init__(self):
        self._mono = 1000.0
        self._wall = datetime(2026, 11, 22, 20, 15, 3, tzinfo=timezone.utc)

    def monotonic(self):
        return self._mono

    def now(self):
        return self._wall

    def advance(self, seconds):
        self._mono += seconds
        self._wall += timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def app(clock):
    from app import create_app

    env = {
        "DEVICE_TOKENS": TEST_TOKENS,
        "REACHABLE_WINDOW_S": "6",
        "PING_DELIVERY_TIMEOUT_S": "10",
        "PING_ACK_TIMEOUT_S": "10",
    }
    return create_app(env=env, clock=clock)


@pytest.fixture
def client(app):
    return app.test_client()
