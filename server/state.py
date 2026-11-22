"""In-memory store: boards, the ping lifecycle, and the lock (DESIGN.md 6.1, 6.4, 6.5).

All state lives in this process. That is why gunicorn must run with exactly one
worker (threads are fine; everything here is guarded by one lock).

Ping lifecycle:  queued -> delivered -> completed
                 queued -> expired    (not picked up within PING_DELIVERY_TIMEOUT_S)
                 delivered -> failed  (not acked within PING_ACK_TIMEOUT_S)

Timeouts are applied lazily whenever state is read or written.
"""

import logging
import secrets
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

log = logging.getLogger("smartlight")

QUEUED = "queued"
DELIVERED = "delivered"
COMPLETED = "completed"
EXPIRED = "expired"
FAILED = "failed"
IN_FLIGHT = (QUEUED, DELIVERED)


class SystemClock:
    """Real clocks. Tests swap in a fake with the same two methods."""

    def monotonic(self):
        return time.monotonic()

    def now(self):
        return datetime.now(timezone.utc)


@dataclass
class Board:
    name: str
    last_seen: float  # monotonic seconds
    last_seen_at: datetime  # wall clock, UTC
    fw: str | None = None
    rssi: int | None = None


@dataclass
class Ping:
    id: str
    t0: float  # monotonic: click
    created_at: datetime  # wall clock of the click, UTC
    status: str = QUEUED
    board: str | None = None
    t1: float | None = None  # monotonic: delivered to a board
    t2: float | None = None  # monotonic: acked by that board


@dataclass
class Store:
    reachable_window_s: float = 6.0
    delivery_timeout_s: float = 10.0
    ack_timeout_s: float = 10.0
    clock: object = field(default_factory=SystemClock)

    def __post_init__(self):
        self._lock = threading.Lock()
        self._boards = {}
        self._latest_board = None
        self._ping = None

    # --- helpers (call with the lock held) ---

    def _set_status(self, ping, status):
        ping.status = status
        log.info("ping %s -> %s%s", ping.id, status, f" ({ping.board})" if ping.board else "")

    def _apply_timeouts(self, now):
        ping = self._ping
        if ping is None:
            return
        if ping.status == QUEUED and now - ping.t0 > self.delivery_timeout_s:
            self._set_status(ping, EXPIRED)
        elif ping.status == DELIVERED and now - ping.t1 > self.ack_timeout_s:
            self._set_status(ping, FAILED)

    def _board_online(self, board, now):
        return board is not None and now - board.last_seen <= self.reachable_window_s

    @staticmethod
    def _ping_view(ping):
        view = {
            "id": ping.id,
            "status": ping.status,
            "board": ping.board,
            "created_at": ping.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        if ping.t1 is not None:
            view["delivery_ms"] = round((ping.t1 - ping.t0) * 1000)
        if ping.t2 is not None:
            view["round_trip_ms"] = round((ping.t2 - ping.t0) * 1000)
        return view

    # --- device side ---

    def poll(self, board_name, fw=None, rssi=None):
        """Record a poll. Returns the response body for the board."""
        with self._lock:
            now = self.clock.monotonic()
            self._apply_timeouts(now)

            board = self._boards.get(board_name)
            if board is None:
                board = Board(board_name, now, self.clock.now())
                self._boards[board_name] = board
            board.last_seen = now
            board.last_seen_at = self.clock.now()
            board.fw = fw
            board.rssi = rssi
            self._latest_board = board_name

            ping = self._ping
            if ping is not None and ping.status == QUEUED:
                ping.t1 = now
                ping.board = board_name
                self._set_status(ping, DELIVERED)
                return {"command": "ping", "ping_id": ping.id}
            return {"command": "none"}

    def ack(self, board_name, ping_id, result="ok"):
        """Record a ping ack. Returns True if accepted, False for an unknown ping."""
        with self._lock:
            now = self.clock.monotonic()
            self._apply_timeouts(now)

            ping = self._ping
            if ping is None or ping.id != ping_id or ping.board != board_name:
                return False
            if ping.status == COMPLETED:
                # A retried ack whose first response was lost. Already recorded.
                return True
            if ping.status != DELIVERED:
                return False

            ping.t2 = now
            self._set_status(ping, COMPLETED if result == "ok" else FAILED)
            return True

    # --- dashboard side ---

    def status(self):
        with self._lock:
            now = self.clock.monotonic()
            self._apply_timeouts(now)

            board_view = None
            board = self._boards.get(self._latest_board)
            if board is not None:
                last_seen_s = now - board.last_seen
                board_view = {
                    "name": board.name,
                    "online": self._board_online(board, now),
                    "last_seen_s": round(last_seen_s, 1),
                    "rssi": board.rssi,
                    "fw": board.fw,
                }
            ping_view = self._ping_view(self._ping) if self._ping else None
            return {"board": board_view, "ping": ping_view}

    def request_ping(self):
        """Queue a ping.

        Returns (ping_view, http_status): 201 for a new ping, 200 when one is
        already in flight (returned instead of a second one), or (None, 409)
        when no board is online.
        """
        with self._lock:
            now = self.clock.monotonic()
            self._apply_timeouts(now)

            board = self._boards.get(self._latest_board)
            if not self._board_online(board, now):
                return None, 409

            if self._ping is not None and self._ping.status in IN_FLIGHT:
                return self._ping_view(self._ping), 200

            ping = Ping(id=secrets.token_hex(4), t0=now, created_at=self.clock.now())
            self._ping = ping
            log.info("ping %s -> %s", ping.id, QUEUED)
            return self._ping_view(ping), 201
