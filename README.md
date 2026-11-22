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

Arduino sketch for the Arduino Nano ESP32 (DESIGN.md Section 5).

### Secrets

Copy `firmware/engr491_smart_light/secrets.example.h` to `secrets.h` in the same folder and fill in:

- `WIFI_SSID` / `WIFI_PASSWORD`: a **2.4 GHz** network (the board can't join a 5 GHz-only network)
- `DEVICE_TOKEN`: this board's token (the same one listed for your name in Railway's `DEVICE_TOKENS`)
- `SERVER_HOST`: the Railway hostname only, without `https://`

`secrets.h` is gitignored. Never commit it.

### Pinned versions

| Component | Version |
|---|---|
| Arduino ESP32 Boards (`arduino:esp32`) | 2.0.18-arduino.5 |
| ArduinoJson (Benoit Blanchon) | 7.4.3 |
| Board (FQBN) | Arduino Nano ESP32 (`arduino:esp32:nano_nora`) |
| Built with | arduino-cli 1.6.0 |

`firmware/engr491_smart_light/sketch.yaml` pins these as the default arduino-cli profile. The installed core is ESP32 Arduino core 2.x, so PWM uses `ledcSetup`/`ledcAttachPin`. Only `light.cpp` would change for core 3.x.

### Build and upload (arduino-cli)

```bash
arduino-cli core install arduino:esp32@2.0.18-arduino.5
arduino-cli lib install ArduinoJson@7.4.3
arduino-cli compile --fqbn arduino:esp32:nano_nora firmware/engr491_smart_light
arduino-cli upload  --fqbn arduino:esp32:nano_nora -p COMx firmware/engr491_smart_light
arduino-cli monitor -p COMx -c baudrate=115200
```

Find the port with `arduino-cli board list`.

### Arduino IDE (Alex)

1. Boards Manager: install **Arduino ESP32 Boards** version **2.0.18-arduino.5**.
2. Library Manager: install **ArduinoJson** version **7.4.3**.
3. Create `secrets.h` (above), open `firmware/engr491_smart_light/engr491_smart_light.ino`, select **Arduino Nano ESP32** and its port, then Upload.
4. Open Serial Monitor at 115200 baud.

**Upload trouble:** the Nano ESP32 uploads over DFU. If an upload fails or the board stops responding, double-press RESET to enter bootloader mode and retry.

### What you should see

- **Onboard RGB:** blinks blue while connecting, shows green once when connected, then turns off. Solid red means Wi-Fi failed, and the board retries after 5 s. The 5 mm LED stays off at boot.
- **Serial:** a `[boot]` line, `[wifi]` status, `[time] syncing ... ok`, then quiet polling. A ping prints `[ping] <id>: running pattern` and `acked`. `token rejected (401)` means the token doesn't match Railway's `DEVICE_TOKENS`.
- **If green and blue look swapped** (some early boards), swap `PIN_RGB_GREEN` and `PIN_RGB_BLUE` in `config.h`.

### Certificate verification

The board checks the server certificate against `root_ca.h`. That file pins the Let's Encrypt roots the Railway chain can end at: ISRG Root X1, ISRG Root X2 and Root YE. `TLS_VERIFY` in `config.h` must stay `1`. `0` is a last-resort fallback that turns verification off and prints a warning at boot.

## Security notes

- Each board has its own random 256-bit token. It is sent as `Authorization: Bearer`, and the server compares it in constant time.
- Tokens live only in each board's `secrets.h` and in Railway variables. They are never logged.
- Before every commit, run `git status` and check that no `secrets.h`, `.env` or real token is staged.
