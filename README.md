# engr491-smart-light

ENGR 491 Engineering Capstone I prototype (Regent University).
Team: Tristan DeOrnellis (software, server, security) and Alex Wang (hardware, circuit, enclosure).

You click **Ping** on a small web dashboard hosted on Railway. An Arduino Nano ESP32 that polls the server over HTTPS picks up the ping. It closes a relay and fades a 5 mm LED up and down 3 times, then reports back. The dashboard shows which board is online, its delivery time and its round-trip time.

The full spec is in [DESIGN.md](DESIGN.md).

> The deployed server URL is intentionally not in this repo (see DESIGN.md Section 8).

## Layout

```
firmware/engr491_smart_light/   Arduino sketch (Phase 2)
server/                         Flask app for Railway
tools/fake_device.py            simulates a board, no hardware needed
```

## Server

### Run locally

Requires Python 3.12 or newer (Railway runs 3.12 from `server/.python-version`).

```bash
cd server
python -m venv .venv
.venv/Scripts/activate          # Windows (Git Bash); on macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt

# Make a token for each board
python -c "import secrets; print(secrets.token_hex(32))"

export DEVICE_TOKENS="tristan:<token>,alex:<token>"   # PowerShell: $env:DEVICE_TOKENS = "..."
flask --app app run
```

Open http://127.0.0.1:5000. If `DEVICE_TOKENS` is missing, the app refuses to start.

Optional variables: `REACHABLE_WINDOW_S` (default 6), `PING_DELIVERY_TIMEOUT_S` (10), `PING_ACK_TIMEOUT_S` (10), `LOG_LEVEL` (INFO; set DEBUG to log every poll).

### Fake device

In a second terminal, from the repo root:

```bash
python tools/fake_device.py --url http://127.0.0.1:5000 --token <token> [--interval 2] [--pattern-seconds 1.5]
```

You can set `FAKE_DEVICE_TOKEN` instead of passing `--token`, which keeps the token out of shell history. Click **Ping** and the script prints the ping, waits 1.5 s and acks. Stop the script and the dashboard shows Offline after about 6 s. A wrong token prints 401s.

### Tests

```bash
cd server
pytest
```

### Deploy on Railway

1. New Project → Deploy from GitHub repo → `engr491-smart-light`.
2. Service settings: **Root Directory** = `server`. `railway.json` sets the start command and the `/healthz` healthcheck.
3. Variables: set `DEVICE_TOKENS` (and the optional timeouts).
4. Networking: **Generate Domain**. Don't commit the address anywhere.
5. Check the live server: `python tools/fake_device.py --url https://<your-domain> --token <token>`.

The start command is `gunicorn app:app --workers 1 --threads 4 --bind 0.0.0.0:$PORT`. **Keep `--workers 1`.** All state is in memory, so a second worker process wouldn't see pings queued in the first. Each deploy restarts the app and clears its state. The board repopulates it on its next poll.

## Firmware

Coming in Phase 2 (DESIGN.md Section 5). Copy `firmware/engr491_smart_light/secrets.example.h` to `secrets.h` and fill in your Wi-Fi details, the board's token and the server hostname. `secrets.h` is gitignored.

### Pinned versions

| Component | Version |
|---|---|
| Arduino ESP32 Boards (`arduino:esp32`) | TBD (Phase 2) |
| ArduinoJson | TBD (Phase 2) |

## Security notes

- Each board has its own random 256-bit token. It is sent as `Authorization: Bearer`, and the server compares it in constant time.
- Tokens live only in each board's `secrets.h` and in Railway variables. They are never logged.
- Before every commit, run `git status` and check that no `secrets.h`, `.env` or real token is staged.
