"""Server tests (DESIGN.md 10, Phase 1 step 4). Run from server/: pytest"""

import pytest

from auth import ConfigError, parse_device_tokens
from conftest import ALEX_TOKEN, TRISTAN_TOKEN


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def poll(client, token=TRISTAN_TOKEN, body=None):
    return client.post("/device/poll", json=body or {"fw": "0.1.0", "rssi": -58}, headers=auth(token))


def ack(client, ping_id, token=TRISTAN_TOKEN):
    return client.post("/device/ack", json={"ping_id": ping_id, "result": "ok"}, headers=auth(token))


def status(client):
    return client.get("/api/status").get_json()


# --- auth ---

@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer "},
    {"Authorization": "Bearer wrong-token"},
    {"Authorization": f"Basic {TRISTAN_TOKEN}"},
    {"Authorization": TRISTAN_TOKEN},
])
@pytest.mark.parametrize("path", ["/device/poll", "/device/ack"])
def test_missing_or_bad_token_is_401(client, path, headers):
    r = client.post(path, json={"fw": "0.1.0", "rssi": -58, "ping_id": "x"}, headers=headers)
    assert r.status_code == 401
    assert r.get_json() == {"error": "unauthorized"}


def test_bad_token_does_not_show_board(client):
    poll(client, token="nope")
    assert status(client)["board"] is None


def test_auth_failure_log_never_contains_token(client, caplog):
    caplog.set_level("DEBUG", logger="smartlight")
    poll(client, token="secret-wrong-token")
    poll(client)
    assert "secret-wrong-token" not in caplog.text
    assert TRISTAN_TOKEN not in caplog.text
    assert "invalid token" in caplog.text


# --- poll ---

def test_poll_returns_none_and_records_board(client, clock):
    assert status(client)["board"] is None

    r = poll(client, body={"fw": "0.1.0", "rssi": -61})
    assert r.status_code == 200
    assert r.get_json() == {"command": "none"}

    clock.advance(1.4)
    board = status(client)["board"]
    assert board == {"name": "tristan", "online": True, "last_seen_s": 1.4, "rssi": -61, "fw": "0.1.0"}


def test_poll_tracks_most_recent_board(client, clock):
    poll(client, token=TRISTAN_TOKEN)
    clock.advance(1)
    poll(client, token=ALEX_TOKEN)
    assert status(client)["board"]["name"] == "alex"
    clock.advance(1)
    poll(client, token=TRISTAN_TOKEN)
    assert status(client)["board"]["name"] == "tristan"


def test_poll_tolerates_missing_body(client):
    r = client.post("/device/poll", headers=auth(TRISTAN_TOKEN))
    assert r.status_code == 200
    board = status(client)["board"]
    assert board["fw"] is None and board["rssi"] is None


# --- online / offline ---

def test_online_offline_threshold(client, clock):
    poll(client)
    clock.advance(6.0)
    assert status(client)["board"]["online"] is True
    clock.advance(0.1)
    board = status(client)["board"]
    assert board["online"] is False
    assert board["name"] == "tristan"  # still shown, just offline


def test_ping_409_when_no_board_has_polled(client):
    r = client.post("/api/ping")
    assert r.status_code == 409
    assert r.get_json() == {"error": "no board online"}
    assert status(client)["ping"] is None


def test_ping_409_when_board_offline(client, clock):
    poll(client)
    clock.advance(7)
    r = client.post("/api/ping")
    assert r.status_code == 409
    assert r.get_json() == {"error": "no board online"}


# --- ping lifecycle ---

def test_full_ping_lifecycle(client, clock):
    poll(client)

    r = client.post("/api/ping")
    assert r.status_code == 201
    ping = r.get_json()
    assert ping["status"] == "queued"
    assert ping["board"] is None
    assert ping["created_at"] == "2026-11-22T20:15:03Z"
    assert len(ping["id"]) == 8
    assert "delivery_ms" not in ping and "round_trip_ms" not in ping

    clock.advance(1.18)
    r = poll(client)
    assert r.get_json() == {"command": "ping", "ping_id": ping["id"]}
    s = status(client)["ping"]
    assert s["status"] == "delivered"
    assert s["board"] == "tristan"
    assert s["delivery_ms"] == 1180
    assert "round_trip_ms" not in s

    # The ping is handed out once only.
    assert poll(client).get_json() == {"command": "none"}

    clock.advance(1.84)
    r = ack(client, ping["id"])
    assert r.status_code == 200
    assert r.get_json() == {"ok": True}

    s = status(client)["ping"]
    assert s["status"] == "completed"
    assert s["delivery_ms"] == 1180
    assert s["round_trip_ms"] == 3020


def test_retried_ack_after_completion_is_ok(client, clock):
    poll(client)
    ping_id = client.post("/api/ping").get_json()["id"]
    poll(client)
    assert ack(client, ping_id).status_code == 200
    assert ack(client, ping_id).status_code == 200
    assert status(client)["ping"]["status"] == "completed"


def test_ping_expires_when_not_picked_up(client, clock):
    poll(client)
    ping_id = client.post("/api/ping").get_json()["id"]
    clock.advance(10.0)
    assert status(client)["ping"]["status"] == "queued"
    clock.advance(0.1)
    s = status(client)["ping"]
    assert s["status"] == "expired"
    assert s["id"] == ping_id

    # A board that comes back later does not replay the expired ping.
    assert poll(client).get_json() == {"command": "none"}


def test_ping_fails_when_not_acked(client, clock):
    poll(client)
    ping_id = client.post("/api/ping").get_json()["id"]
    poll(client)
    clock.advance(10.1)
    assert status(client)["ping"]["status"] == "failed"
    # A late ack is refused.
    assert ack(client, ping_id).status_code == 409
    assert status(client)["ping"]["status"] == "failed"


def test_second_ping_while_in_flight_returns_same_ping(client, clock):
    poll(client)
    first = client.post("/api/ping")
    assert first.status_code == 201

    again = client.post("/api/ping")
    assert again.status_code == 200
    assert again.get_json()["id"] == first.get_json()["id"]

    poll(client)  # now delivered
    still = client.post("/api/ping")
    assert still.status_code == 200
    assert still.get_json()["id"] == first.get_json()["id"]
    assert still.get_json()["status"] == "delivered"


def test_new_ping_allowed_after_completion(client, clock):
    poll(client)
    first_id = client.post("/api/ping").get_json()["id"]
    poll(client)
    ack(client, first_id)
    r = client.post("/api/ping")
    assert r.status_code == 201
    assert r.get_json()["id"] != first_id


def test_ack_with_wrong_ping_id_is_409(client):
    poll(client)
    client.post("/api/ping")
    poll(client)
    r = ack(client, "deadbeef")
    assert r.status_code == 409
    assert r.get_json() == {"error": "unknown ping"}
    assert status(client)["ping"]["status"] == "delivered"


def test_ack_from_different_board_is_409(client):
    poll(client, token=TRISTAN_TOKEN)
    ping_id = client.post("/api/ping").get_json()["id"]
    poll(client, token=TRISTAN_TOKEN)
    r = ack(client, ping_id, token=ALEX_TOKEN)
    assert r.status_code == 409
    assert r.get_json() == {"error": "unknown ping"}
    assert status(client)["ping"]["status"] == "delivered"


def test_ack_before_delivery_is_409(client):
    poll(client)
    ping_id = client.post("/api/ping").get_json()["id"]
    assert ack(client, ping_id).status_code == 409
    assert status(client)["ping"]["status"] == "queued"


def test_ack_with_missing_ping_id_is_409(client):
    poll(client)
    r = client.post("/device/ack", json={}, headers=auth(TRISTAN_TOKEN))
    assert r.status_code == 409


def test_any_authenticated_board_can_pick_up_ping(client):
    poll(client, token=TRISTAN_TOKEN)
    ping_id = client.post("/api/ping").get_json()["id"]
    assert poll(client, token=ALEX_TOKEN).get_json()["command"] == "ping"
    assert ack(client, ping_id, token=ALEX_TOKEN).status_code == 200
    assert status(client)["ping"]["board"] == "alex"


# --- startup config ---

@pytest.mark.parametrize("env", [{}, {"DEVICE_TOKENS": ""}, {"DEVICE_TOKENS": "  , "}])
def test_app_refuses_to_start_without_device_tokens(env):
    from app import create_app

    with pytest.raises(ConfigError):
        create_app(env=env)


@pytest.mark.parametrize("raw", ["justatoken", "tristan:", ":abc", "a:1,a:2"])
def test_malformed_device_tokens_rejected(raw):
    with pytest.raises(ConfigError) as exc:
        parse_device_tokens(raw)
    assert "abc" not in str(exc.value)


def test_device_tokens_parsed():
    assert parse_device_tokens(" tristan:abc , alex:def ") == [("tristan", "abc"), ("alex", "def")]


# --- misc ---

def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_data(as_text=True) == "ok"


def test_dashboard_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"ENGR 491 Smart Light (Prototype)" in r.data
    assert b"Simulates someone trying to reach you." in r.data
