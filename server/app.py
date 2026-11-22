"""Flask app: device endpoints, dashboard endpoints, healthcheck (DESIGN.md 6).

Run locally:   flask --app app run            (from server/, with DEVICE_TOKENS set)
Production:    gunicorn app:app --workers 1 --threads 4 --bind 0.0.0.0:$PORT

Keep --workers at 1. All state is in memory (state.py); a second worker process
would not see pings queued in the first.

Device endpoints (/device/poll, /device/ack) are a contract compiled into the
firmware. Add fields; don't rename or remove them.
"""

import logging
import os

from flask import Flask, jsonify, render_template, request

from auth import bearer_token, board_for_token, parse_device_tokens
from state import Store, SystemClock

log = logging.getLogger("smartlight")


def _float_env(env, name, default):
    value = env.get(name)
    return float(value) if value not in (None, "") else default


def create_app(env=None, clock=None):
    """Build the app. Raises auth.ConfigError if DEVICE_TOKENS is missing or bad."""
    env = os.environ if env is None else env
    tokens = parse_device_tokens(env.get("DEVICE_TOKENS"))

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=env.get("LOG_LEVEL", "INFO").upper(),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )

    store = Store(
        reachable_window_s=_float_env(env, "REACHABLE_WINDOW_S", 6.0),
        delivery_timeout_s=_float_env(env, "PING_DELIVERY_TIMEOUT_S", 10.0),
        ack_timeout_s=_float_env(env, "PING_ACK_TIMEOUT_S", 10.0),
        clock=clock or SystemClock(),
    )

    app = Flask(__name__)
    app.config["STORE"] = store
    log.info("loaded %d device token(s) for: %s", len(tokens), ", ".join(n for n, _ in tokens))

    def client_ip():
        # Railway sits behind a proxy; the first X-Forwarded-For hop is the client.
        forwarded = request.headers.get("X-Forwarded-For", "")
        return forwarded.split(",")[0].strip() or request.remote_addr

    def authenticated_board():
        name = board_for_token(bearer_token(request.headers.get("Authorization")), tokens)
        if name is None:
            log.info("auth failure from %s: invalid token", client_ip())
        return name

    def unauthorized():
        return jsonify(error="unauthorized"), 401

    # --- device endpoints ---

    @app.post("/device/poll")
    def device_poll():
        board = authenticated_board()
        if board is None:
            return unauthorized()
        body = request.get_json(silent=True) or {}
        fw = body.get("fw")
        fw = str(fw)[:32] if fw is not None else None
        rssi = body.get("rssi")
        rssi = rssi if isinstance(rssi, int) and not isinstance(rssi, bool) else None
        response = store.poll(board, fw=fw, rssi=rssi)
        log.debug("poll from %s fw=%s rssi=%s -> %s", board, fw, rssi, response["command"])
        return jsonify(response)

    @app.post("/device/ack")
    def device_ack():
        board = authenticated_board()
        if board is None:
            return unauthorized()
        body = request.get_json(silent=True) or {}
        ping_id = body.get("ping_id")
        result = body.get("result", "ok")
        if not isinstance(ping_id, str) or not store.ack(board, ping_id, result):
            return jsonify(error="unknown ping"), 409
        return jsonify(ok=True)

    # --- dashboard endpoints (no auth, R12) ---

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def api_status():
        return jsonify(store.status())

    @app.post("/api/ping")
    def api_ping():
        ping, status = store.request_ping()
        if ping is None:
            return jsonify(error="no board online"), 409
        return jsonify(ping), status

    @app.get("/healthz")
    def healthz():
        return "ok", 200, {"Content-Type": "text/plain"}

    @app.after_request
    def no_cache_api(response):
        if request.path.startswith(("/api/", "/device/")):
            response.headers["Cache-Control"] = "no-store"
        return response

    return app


app = create_app()
