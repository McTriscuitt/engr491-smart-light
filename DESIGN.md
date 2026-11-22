# engr491-smart-light: Prototype Design (Iteration 1)

**Project:** ENGR 491 Engineering Capstone I, Regent University
**Team:** Tristan DeOrnellis (software, server, security) and Alex Wang (hardware, circuit, enclosure)
**Status:** Approved requirements, ready to implement
**Deadline:** End of day, Sunday 2026-11-22 (this week's submission must be testable)

---

## 0. How to use this document (for the implementing Code session)

This document is the full spec for iteration 1. Build exactly what is here.

- **Don't add scope.** Section 2 lists what is out. If something seems missing, ask Tristan rather than inventing it.
- **Two kinds of decisions appear below.** Items marked **[Team]** were decided by Tristan and Alex and are fixed. Items marked **[Design]** are implementation defaults chosen in this doc; they can change if there is a concrete reason, but say so in the commit message and update this file.
- **Verify library APIs against the installed versions.** Don't assume an API from memory (see the LEDC note in 5.6). Record the exact versions you build with (Section 5.1).
- **Never commit secrets.** The repo is public. Section 8 lists what must stay out of Git, including the server URL.
- **Pins belong to Alex.** If Alex wires different pins, change `config.h` only.
- Follow the phase plan in Section 10 and stop at each checkpoint for Tristan.

---

## 1. Purpose

Prove the end-to-end path works: a browser click on a Railway-hosted dashboard reaches an Arduino Nano ESP32 over the internet, and the board visibly drives a 5 mm LED through a relay with PWM dimming, then reports back.

The long-term product is a physical "Do Not Disturb bypass" alert light: a way for someone to get the user's attention when their phone is silenced. In this iteration, the dashboard's **Ping** button stands in for "someone is trying to reach the user." **[Team]**

---

## 2. Scope

### In scope (iteration 1)

| # | Requirement | Source |
|---|---|---|
| R1 | Arduino Nano ESP32 (ABX00083) powered from a laptop over USB-C | [Team] |
| R2 | 5 mm LED driven by PWM directly from a GPIO pin through a resistor | [Team] |
| R3 | SRD-05VDC-SL-C relay (bare relay) in series with the LED as a master on/off switch, coil on VBUS (5 V), driven by a PN2222 with a 1N4007 flyback diode | [Team] |
| R4 | Firmware in C++ on the Arduino ESP32 core, as a standard Arduino sketch (buildable with `arduino-cli` and the Arduino IDE) | [Team] |
| R5 | Board joins the owner's home Wi-Fi; credentials and token in a gitignored `secrets.h` | [Team] |
| R6 | Startup: onboard RGB LED blinks blue while connecting, flashes green once when connected, shows red and retries on failure. The 5 mm LED stays off at boot | [Team] |
| R7 | Board polls the server over HTTPS (every 1 to 2 s) and verifies the server's certificate | [Team] |
| R8 | Each board (Tristan's, Alex's) has its own name and secret token. Only one board runs at a time | [Team] |
| R9 | Ping: relay on, LED quickly fades up and down 3 times (about 0.5 s per cycle, about 1.5 s total), relay off, board reports completion | [Team] |
| R10 | Dashboard (Flask on Railway, default `*.up.railway.app` domain): one page, one Ping button. Shows which board checked in last, reachable or not, round-trip time, last seen | [Team] |
| R11 | Board is "unreachable" after about 3 missed polls | [Team] |
| R12 | No database, no dashboard login. Board-facing endpoints only; no public API | [Team] |
| R13 | Public GitHub repo `engr491-smart-light` on Tristan's account | [Team] |

### Out of scope (do not build)

Scheduling, multiple users and permissions, power or activity reports, conflict handling, database, dashboard login, public API for outside apps, on/off or brightness controls on the dashboard, over-the-air firmware updates, wiring diagram (Alex owns it), enclosure.

---

## 3. System overview

```
 ┌──────────────┐  HTTPS (browser)   ┌───────────────────────────┐
 │  Dashboard   │ ─────────────────► │  Railway: Flask + gunicorn │
 │  (browser)   │ ◄───────────────── │  (1 worker, in-memory)     │
 └──────────────┘  /api/status 1 s   └─────────────▲─────────────┘
                                                   │ HTTPS, Bearer token
                                                   │ POST /device/poll every 2 s
                                                   │ POST /device/ack
                                     ┌─────────────┴─────────────┐
                                     │ Arduino Nano ESP32         │
                                     │  GPIO ─R─ relay ─ 5 mm LED │
                                     │  GPIO ─ PN2222 ─ relay coil│
                                     └───────────────────────────┘
                                       (behind home router / NAT)
```

The board is behind a home router, so the server can't reach it directly. The board always starts the connection by polling. **[Team: simple HTTPS, can change later]**

### Ping sequence

```
Browser          Server                         Board
   │ POST /api/ping │                               │
   │──────────────► │ ping = queued (t0)            │
   │                │ ◄──── POST /device/poll ───── │ (within ≤2 s)
   │                │ ping = delivered (t1)         │
   │                │ ───── {"command":"ping"} ───► │
   │                │                               │ relay on, 3 fades (~1.5 s), relay off
   │                │ ◄──── POST /device/ack ────── │
   │                │ ping = completed (t2)         │
   │ GET /api/status│                               │
   │──────────────► │ delivery = t1−t0, RTT = t2−t0 │
```

**Round-trip time** is defined as click to ack (`t2 − t0`). It includes waiting for the next poll and the 1.5 s light pattern, so expect roughly 2 to 4 s. The dashboard also shows **delivery time** (`t1 − t0`) so the network part is visible on its own. **[Design]**

---

## 4. Hardware

Alex owns the circuit and the wiring diagram. This section records the electrical constraints the firmware depends on.

### 4.1 Board facts (from the ABX00083 datasheet and pinout)

- **Logic level:** all GPIOs are 3.3 V. Nothing above 3.3 V may connect to a pin.
- **Pin current:** each GPIO can source up to 40 mA and sink up to 28 mA.
- **5 V:** there is no 5 V pin. VBUS provides 5 V only while the board is powered over USB-C, which is the case here (R1).
- **Wi-Fi:** 802.11 b/g/n, **2.4 GHz only**. The board can't join a 5 GHz-only network. A router that combines 2.4 and 5 GHz under one name usually works.
- **Pins to avoid:**
  - D0 and D1 (UART; D1/TX has a 499 Ω series resistor).
  - B0 and B1 (tied to the onboard RGB LED).
  - A2/GPIO3 (ESP32-S3 strapping pin).
  - D13/GPIO48 (onboard LED and SPI clock).
- **Onboard RGB LED:** red GPIO46 (`LED_RED`), green GPIO0 (`LED_GREEN`), blue GPIO45 (`LED_BLUE`). It is common-anode to 3V3, so it is **active-low** (LOW turns a color on). The pinout notes that some boards from the first production batch have green and blue swapped; confirm on first flash and swap the constants in `config.h` if needed.

### 4.2 Pin assignment **[Design, Alex may change]**

| Function | Arduino pin | GPIO | Notes |
|---|---|---|---|
| LED PWM output | D3 | GPIO6 | Through series resistor and relay contacts to the LED |
| Relay driver | D2 | GPIO5 | To PN2222 base through a resistor. HIGH = relay energized |
| Status (RGB) | LED_RED / LED_GREEN / LED_BLUE | 46 / 0 / 45 | Onboard, active-low |


<img width="1082" height="783" alt="image" src="https://github.com/user-attachments/assets/0f454430-803d-4f85-8d77-bfd99e2c8d18" />


Firmware uses Arduino pin names (`D2`, `D3`) with the core's default "by Arduino pin" numbering.

### 4.3 Circuit constraints (reference for Alex, not a diagram)

- **LED current:** keep it at or under about 15 to 20 mA. With 3.3 V from the pin, a 220 Ω resistor from the kit gives roughly 5 to 7 mA for a red LED, which is bright enough and well under the 40 mA pin limit.
- **LED path (R2, R3):** PWM pin → series resistor → relay COM → relay NO → LED anode → LED cathode → GND. When the relay is open, the LED is off no matter what the PWM pin does.
- **Relay coil:** about 70 mA at 5 V (per Songle's SRD datasheet). That's too much for a GPIO, so the PN2222 switches it:
  - Relay coil goes between VBUS and the PN2222 collector; the emitter goes to GND.
  - Base resistor of about 1 kΩ from D2. That gives about 2.6 mA of base current, enough to saturate the transistor at 70 mA.
  - 1N4007 across the coil, **stripe (cathode) toward VBUS**, to absorb the voltage spike when the coil turns off.
- **Relay pins:** identify the coil, COM, NO and NC legs from the relay's markings or datasheet (or a continuity check) before wiring.
- **Power budget on laptop USB:** board up to a few hundred mA during Wi-Fi transmit, plus about 70 mA for the coil and under 20 mA for the LED. That's roughly 400 to 450 mA peak, under the 500 mA a USB 2.0 port must supply.

---

## 5. Firmware

### 5.1 Toolchain **[Team: arduino-cli for Tristan, Arduino IDE must also work for Alex]**

- **Board package:** "Arduino ESP32 Boards" (`arduino:esp32`). Expected FQBN: `arduino:esp32:nano_nora`. Verify with `arduino-cli board listall nano`.
- **Library:** ArduinoJson (by Benoit Blanchon), v7.x.
- **Version pinning:** after installing, record the exact platform and library versions in `firmware/engr491_smart_light/sketch.yaml` (an arduino-cli profile) and in the README, so Alex installs the same ones in the IDE.
- **Build and upload (terminal):**
  ```
  arduino-cli core install arduino:esp32
  arduino-cli lib install ArduinoJson
  arduino-cli compile --fqbn arduino:esp32:nano_nora firmware/engr491_smart_light
  arduino-cli upload  --fqbn arduino:esp32:nano_nora -p COMx firmware/engr491_smart_light
  arduino-cli monitor -p COMx -c baudrate=115200
  ```
- **Arduino IDE (Alex):** open `firmware/engr491_smart_light/engr491_smart_light.ino`, select **Arduino Nano ESP32**, install ArduinoJson from Library Manager, then Upload.
- **Upload troubleshooting:** the Nano ESP32 uploads over DFU. If an upload fails or the board stops responding, double-press RESET to enter bootloader mode and retry. On Windows, if `arduino-cli` can't see the board in DFU mode, installing the Arduino IDE once usually installs the needed drivers.

### 5.2 Sketch layout

```
firmware/engr491_smart_light/
  engr491_smart_light.ino   setup(), loop(), top-level state machine
  config.h                  pins, timing constants, firmware version (committed)
  secrets.example.h         template (committed)
  secrets.h                 real values (GITIGNORED)
  root_ca.h                 server root CA certificate(s), PEM (committed; public data)
  status_led.h/.cpp         RGB status patterns (non-blocking)
  light.h/.cpp              relay + PWM control and the ping pattern
  net.h/.cpp                Wi-Fi connect/reconnect, HTTPS poll and ack
  sketch.yaml               arduino-cli profile with pinned versions
```

### 5.3 `secrets.h` (from `secrets.example.h`) **[Team]**

```cpp
#pragma once
#define WIFI_SSID     "your-2.4GHz-network"
#define WIFI_PASSWORD "your-password"
#define DEVICE_TOKEN  "64-hex-char token issued for this board"
#define SERVER_HOST   "your-app.up.railway.app"   // hostname only, no https://
```

`SERVER_HOST` lives in `secrets.h`, not `config.h`, because the repo is public and the dashboard has no login. Keeping the URL out of the repo is what limits it to Tristan, Alex and the professor (see Section 8).

The board's display name ("tristan" or "alex") is not in firmware. The server derives it from the token.

### 5.4 `config.h` constants **[Design]**

| Constant | Value | Meaning |
|---|---|---|
| `FW_VERSION` | `"0.1.0"` | Reported in each poll |
| `PIN_LED_PWM` | `D3` | See 4.2 |
| `PIN_RELAY` | `D2` | See 4.2 |
| `PWM_FREQ_HZ` | `5000` | Flicker-free for an LED |
| `PWM_RES_BITS` | `8` | Duty 0 to 255 |
| `PING_CYCLES` | `3` | R9 |
| `PING_HALF_CYCLE_MS` | `250` | Fade up 250 ms, fade down 250 ms |
| `RELAY_SETTLE_MS` | `20` | Relay operate time is under 10 ms; 20 ms margin |
| `POLL_INTERVAL_MS` | `2000` | R7 |
| `HTTP_TIMEOUT_MS` | `5000` | Per request |
| `WIFI_CONNECT_TIMEOUT_MS` | `20000` | Before showing red |
| `WIFI_RETRY_DELAY_MS` | `5000` | Red shown during this wait, then retry |
| `AUTH_FAIL_BACKOFF_MS` | `10000` | Poll slower after a 401 so a bad token doesn't spam the server |
| `TLS_VERIFY` | `1` | See 5.8. Set to 0 only as a last-resort fallback |

### 5.5 Behavior

**Boot (first lines of `setup()`, before anything else):**
1. `PIN_RELAY` set as OUTPUT and driven LOW (relay off).
2. PWM attached to `PIN_LED_PWM` with duty 0.
3. RGB LED all off.
4. Serial at 115200 for logs.

The 5 mm LED must never light at boot. **[Team]**

**Wi-Fi states (RGB LED):**

| State | RGB LED | Exit |
|---|---|---|
| CONNECTING | Blue blinking about 2 Hz | Connected → CONNECTED_FLASH. Timeout → WIFI_FAILED |
| CONNECTED_FLASH | Green solid about 500 ms, once | → RUNNING |
| WIFI_FAILED | Red solid | After `WIFI_RETRY_DELAY_MS` → CONNECTING |
| RUNNING | Off | Wi-Fi lost → CONNECTING |

- Use `WiFi.mode(WIFI_STA)`.
- The RGB patterns are non-blocking (driven from `loop()` with `millis()`).
- Server or HTTP errors during RUNNING are logged to Serial only. No extra RGB state in this iteration.

**Time sync:** after connecting, call `configTime(0, 0, "pool.ntp.org", "time.nist.gov")` and wait up to 10 s for a valid time. Some TLS setups check certificate dates, and this removes that failure mode. Continue even if the sync times out, but log it.

**RUNNING loop:**
1. Every `POLL_INTERVAL_MS`, `POST https://SERVER_HOST/device/poll` (format in 6.4).
2. If the response is `{"command":"ping","ping_id":...}`, run the ping pattern (5.6), then `POST /device/ack`. If the ack fails, retry once.
3. If the response is `{"command":"none"}`, do nothing.
4. On 401, log "token rejected" and wait `AUTH_FAIL_BACKOFF_MS` before polling again.
5. On any other error or timeout, log it and keep polling at the normal interval.

The ping pattern may block for its 1.5 s; polling pauses during it. That's acceptable for this iteration.

### 5.6 Ping pattern **[Team: 3 quick fades, about 1.5 s; Design: timing details]**

```
relay ON  → wait RELAY_SETTLE_MS
repeat PING_CYCLES times:
    fade duty 0 → 255 over PING_HALF_CYCLE_MS   (~50 steps, ~5 ms each)
    fade duty 255 → 0 over PING_HALF_CYCLE_MS
duty 0 → relay OFF
```

- **Smoother fades (recommended):** apply a simple perceptual curve, `duty = (step * step) / 255` for a linear `step` of 0 to 255. Without it, the LED looks bright for most of the fade.
- **LEDC API check:** the ESP32 Arduino core changed its PWM API between major versions. Core 2.x uses `ledcSetup(channel, freq, bits)` and `ledcAttachPin(pin, channel)`, then `ledcWrite(channel, duty)`. Core 3.x uses `ledcAttach(pin, freq, bits)`, then `ledcWrite(pin, duty)`. Check which one the installed `arduino:esp32` platform exposes and use that. Put it behind small `lightInit()` and `lightSetDuty()` functions so the rest of the code doesn't care.

### 5.7 HTTPS client

- Use `WiFiClientSecure` plus `HTTPClient`, and keep one client alive across polls (`http.setReuse(true)`). That avoids a full TLS handshake every 2 seconds. If a request fails, close it and reconnect on the next poll.
- **Headers:**
  - `Authorization: Bearer <DEVICE_TOKEN>`
  - `Content-Type: application/json`
- Build JSON bodies and parse responses with ArduinoJson.
- **Never print `DEVICE_TOKEN` or `WIFI_PASSWORD` to Serial.**

### 5.8 Certificate verification **[Team: HTTPS now; Design: method]**

- Call `client.setCACert(ROOT_CA_PEM)` with the PEM in `root_ca.h`.
- **Getting the root CA (Phase 2, after the first Railway deploy):**
  ```
  openssl s_client -connect <SERVER_HOST>:443 -servername <SERVER_HOST> -showcerts </dev/null
  ```
  On Windows, Git Bash includes `openssl`. Identify the issuing **root** CA from the chain, download that root's PEM from the CA's official site, and place it in `root_ca.h`. Pin the root, not the leaf, so certificate renewals don't break the board. If the chain could end at more than one root (cross-signed), concatenate both root PEMs into the one string.
- **[Design] What was pinned (2026-11-22):** Railway serves `*.up.railway.app` ← Let's Encrypt YE2 ← Root YE (cross-signed by ISRG Root X2) ← ISRG Root X2 (cross-signed by ISRG Root X1). `root_ca.h` holds all three roots: X1, X2 and Root YE. Each verified the live chain on its own, so the board keeps working if Let's Encrypt shortens the chain.
- **Fallback, last resort only:** if verification blocks the deadline, build with `TLS_VERIFY 0`, which calls `client.setInsecure()`. The board must then print a loud warning at boot. The submission write-up must state that verification is temporarily off. Default is `TLS_VERIFY 1`.

---

## 6. Server and dashboard

### 6.1 Stack **[Team: Python + Flask on Railway; Design: the rest]**

- Python 3.12 (pin with a `.python-version` file; confirm Railway's builder honors it, otherwise set it the way Railway's docs say).
- Flask and gunicorn, listed in `requirements.txt`.
- **Start command:** `gunicorn app:app --workers 1 --threads 4 --bind 0.0.0.0:$PORT`
- **Why one worker:** all state is in memory. With more than one worker process, a ping queued in one process would be invisible to the process that answers the board's poll. **Do not raise `--workers`.** Threads share memory, so 4 threads is fine; guard state with a `threading.Lock`.
- **Restarts:** Railway restarts the app on every deploy, which clears the state. That's acceptable: the board's next poll repopulates "last seen" within 2 seconds.

### 6.2 Layout

```
server/
  app.py               Flask app, routes
  state.py             in-memory store, ping lifecycle, lock
  auth.py              token parsing and checking
  templates/index.html dashboard page
  static/dashboard.js  polls /api/status, handles the Ping button
  static/style.css     minimal styling
  requirements.txt
  requirements-dev.txt adds pytest and requests for local work
  pytest.ini
  .python-version
  railway.json         start command + healthcheck path (or Procfile)
  tests/conftest.py    fixtures, fake clock
  tests/test_app.py    pytest
tools/
  fake_device.py       simulates a board against local or deployed server
```

### 6.3 Configuration (Railway environment variables)

| Variable | Example | Notes |
|---|---|---|
| `DEVICE_TOKENS` | `tristan:3f9a...,alex:b71c...` | Comma-separated `name:token` pairs. Required; app refuses to start without at least one |
| `REACHABLE_WINDOW_S` | `6` | 3 missed polls at 2 s (R11) |
| `PING_DELIVERY_TIMEOUT_S` | `10` | Queued ping not picked up → `expired` |
| `PING_ACK_TIMEOUT_S` | `10` | Delivered ping not acked → `failed` |

Generate each token with:
`python -c "import secrets; print(secrets.token_hex(32))"`

The same token goes into that board's `secrets.h`.

### 6.4 Device endpoints (board only, Bearer token required)

Every device request: parse `Authorization: Bearer <token>`, compare against each configured token with `hmac.compare_digest`, and resolve the board name. Unknown or missing token returns `401 {"error":"unauthorized"}`.

**`POST /device/poll`**

Request body:
```json
{ "fw": "0.1.0", "rssi": -58 }
```

The server records `last_seen` (wall clock and monotonic), `fw` and `rssi` for that board, and marks that board as the most recently seen.

If a ping is `queued`, the server marks it `delivered`, records `t1` and the board name, and responds:
```json
{ "command": "ping", "ping_id": "a1b2c3d4" }
```
Otherwise it responds:
```json
{ "command": "none" }
```

Any authenticated board can pick up a queued ping (only one board runs at a time, R8).

`command` is a generic field on purpose: later iterations can add commands such as on, off or brightness without changing the endpoint.

**`POST /device/ack`**

Request body:
```json
{ "ping_id": "a1b2c3d4", "result": "ok" }
```

- If `ping_id` matches the in-flight ping and it was delivered to this same board, mark it `completed` and record `t2`. Responds `200 {"ok": true}`.
- A mismatched or unknown ID returns `409 {"error":"unknown ping"}`.
- **[Design]** A repeated ack for a ping this board already completed returns `200` again. That keeps the firmware's single ack retry (5.5) safe when the first response was lost. A `result` other than `"ok"` marks the ping `failed`.

### 6.5 Dashboard endpoints (used only by the page's JavaScript, no auth per R12)

**`GET /`** serves the dashboard HTML.

**`GET /api/status`**

```json
{
  "board": {
    "name": "tristan",
    "online": true,
    "last_seen_s": 1.4,
    "rssi": -58,
    "fw": "0.1.0"
  },
  "ping": {
    "id": "a1b2c3d4",
    "status": "completed",
    "board": "tristan",
    "created_at": "2026-11-22T20:15:03Z",
    "delivery_ms": 1180,
    "round_trip_ms": 3020
  }
}
```

- `board` is the most recently seen board, or `null` if no board has polled since the server started. `online` is true when `last_seen_s <= REACHABLE_WINDOW_S`.
- `ping` is the latest ping, or `null`. `status` is one of `queued`, `delivered`, `completed`, `expired` or `failed`. `delivery_ms` and `round_trip_ms` are present once known.
- Timeouts are evaluated lazily whenever state is read or written; no background thread is needed.

**`POST /api/ping`**

- If no board is online: `409 {"error":"no board online"}`. The page shows "No board online."
- If a ping is already `queued` or `delivered`: return that ping with `200` rather than creating a second one, so only one ping is in flight at a time.
- Otherwise create a new ping (`status: queued`, `t0` = now, short random ID) and return it with `201`.

**`GET /healthz`** returns `200 ok` for Railway's healthcheck.

### 6.6 Dashboard page **[Team: very rough, Ping only]**

One plain page, no frontend build step, vanilla JavaScript.

- **Title:** "ENGR 491 Smart Light (Prototype)"
- **Board card:**
  - board name, or "No board has checked in"
  - Online or Offline indicator
  - "Last seen N s ago"
  - small grey line with firmware version and RSSI
- **Ping button,** with the caption "Simulates someone trying to reach you." Disabled while a ping is queued or delivered.
- **Last ping:**
  - status (Queued, Delivered, Completed, Expired, Failed)
  - which board answered
  - delivery time and round-trip time in ms
  - time of the click, shown in local time
- `dashboard.js` fetches `/api/status` every 1 s and on each button click.

Keep the styling minimal and readable on a phone. Polish isn't a goal this iteration.

### 6.7 Logging

Log each poll at debug level, and each ping state change and auth failure at info level. **Never log tokens.** For auth failures, log only the request IP and "invalid token."

### 6.8 Railway deploy (Tristan does these steps in the Railway UI) **[Team]**

1. New Project → Deploy from GitHub repo → `engr491-smart-light`.
2. **Service settings:**
   - Root Directory = `server`
   - Start command from `railway.json` (or set it manually as in 6.1)
   - Healthcheck path `/healthz`
3. **Variables:** set `DEVICE_TOKENS` (and the optional timeouts).
4. **Networking:** Generate Domain to get the `*.up.railway.app` address. Do not put this address in the repo.
5. Run `tools/fake_device.py` against the live URL to confirm before flashing the boards.

---

## 7. `tools/fake_device.py`

A small script with no dependencies beyond `requests`. It lets the dashboard be tested with no hardware.

```
python tools/fake_device.py --url http://127.0.0.1:5000 --token <token> [--interval 2] [--pattern-seconds 1.5]
```

- Polls `/device/poll` with the same body format the board uses.
- On a ping, it sleeps for the pattern time and then acks, just like the board.
- Prints each poll result.
- Testing reachability: stop the script and the dashboard should show Offline after about 6 s.
- Testing auth: pass a wrong token and it should print 401 responses.

---

## 8. Security **[Team: secret token per board, HTTPS, no login]**

| Item | Rule |
|---|---|
| Device auth | One random 256-bit token per board, sent as a Bearer header, compared in constant time. The server maps token → board name |
| Transport | HTTPS only. Railway terminates TLS; the board verifies the certificate against a pinned root CA (5.8) |
| Secrets in the repo | `secrets.h` is gitignored. `secrets.example.h` has placeholders only. Tokens live only in each `secrets.h` and in Railway variables |
| Server URL | Not committed anywhere (not in README, code or this doc's examples). Accepted risk: the dashboard is open to anyone with the URL, which only Tristan, Alex and the professor have **[Team]** |
| Abuse limits | Only one ping can be in flight. Bad tokens get 401, and the board backs off |
| Logs | No tokens or passwords in server logs or Serial output |
| Before every commit | `git status` and a quick check that no `secrets.h`, `.env` or real token is staged |

**Root `.gitignore` must include:**
- `firmware/**/secrets.h`
- `.env`
- `__pycache__/`
- `.venv/`
- `*.pyc`
- `build/`
- `.idea/`
- `.vscode/`

---

## 9. Repository layout

```
engr491-smart-light/
  README.md          what it is, how to build/flash/run/test, pinned versions (no server URL)
  DESIGN.md          this document
  .gitignore
  firmware/engr491_smart_light/   (Section 5.2)
  server/                         (Section 6.2)
  tools/fake_device.py
```

Create the repo with the GitHub CLI: `gh repo create engr491-smart-light --public --source . --push` (on Tristan's account, authenticated as him). **[Team: public, Tristan's account]**

---

## 10. Implementation plan

### Session split recommendation

One Code session can likely build all of this, since the total is a few hundred lines of firmware and server code. There is a natural break, though: the firmware needs the live server's hostname and root CA, and those exist only after Tristan deploys. Use that as the split point if the first session's context is getting heavy:

- **Session A:** Phases 0 and 1 (repo, server, tests, fake device), then Checkpoint A.
- **Session B:** Phase 2 (firmware), then Checkpoint B. Start it by reading this file and the README.

If one session has room, it continues straight through. Either way, this file is the handoff.

### Phase 0: Scaffold

1. Create the folder structure (Section 9), `.gitignore`, README skeleton, and this `DESIGN.md`.
2. `git init`, first commit, then `gh repo create` (Section 9).

### Phase 1: Server

1. Implement `state.py`, `auth.py` and `app.py` per Section 6.
2. Build the dashboard page and JavaScript.
3. Write `tools/fake_device.py`.
4. **Tests (pytest + Flask test client):**
   - missing or bad token → 401
   - poll updates `last_seen` and the most recent board
   - full ping lifecycle (queued → delivered → completed) with correct `delivery_ms` and `round_trip_ms`
   - `expired` when not picked up
   - `failed` when not acked
   - second `POST /api/ping` while in flight returns the same ping
   - `409` when no board is online
   - ack with the wrong `ping_id` or from a different board → 409
   - online/offline threshold
   - app refuses to start without `DEVICE_TOKENS`

   Use an injectable clock so the timing tests don't sleep.
5. Run locally: `flask --app app run` from `server/`, plus `fake_device.py`. Click Ping in the browser and confirm the full cycle.
6. Commit and push.

**Checkpoint A (Tristan):** deploy on Railway (6.8), set the tokens, generate the domain, and run `fake_device.py` against the live URL. Then give the implementing session the hostname (in chat, not committed) so it can fetch the root CA.

### Phase 2: Firmware

1. Install the toolchain (5.1), check the LEDC API version (5.6) and record the versions in `sketch.yaml` and README.
2. Implement the modules (5.2) and `root_ca.h` (5.8).
3. Compile cleanly with `arduino-cli`.
4. Flash Tristan's board and watch the Serial monitor.
5. Commit and push (with `secrets.h` excluded).

**Checkpoint B (Tristan and Alex):** Alex's circuit is wired. Run the acceptance tests in Section 11 on Tristan's board. Then Alex copies `secrets.example.h` to `secrets.h` with his Wi-Fi details and token, flashes from the Arduino IDE, and repeats the board-switch test.

---

## 11. Acceptance tests (this week's submission)

| # | Test | Pass condition |
|---|---|---|
| A1 | Power on over USB-C | RGB blinks blue, then green once, then off. The 5 mm LED stays off the whole time |
| A2 | Wrong Wi-Fi password | RGB shows red, then retries with blue blinking |
| A3 | Dashboard after boot | Shows the right board name, Online, last seen under 3 s |
| A4 | Click Ping | Relay clicks, LED fades up and down 3 times (about 1.5 s), relay clicks off. Dashboard shows Completed with delivery time and round-trip time (expect about 2 to 4 s) |
| A5 | Unplug the board | Dashboard shows Offline within about 6 to 8 s. Ping button returns "No board online" |
| A6 | Switch boards | Alex's board powered instead: dashboard shows "alex" and pings complete |
| A7 | Bad token | Board logs "token rejected" and backs off. Server returns 401 and the dashboard does not show the board |
| A8 | Click Ping twice fast | Only one ping runs |
| A9 | Repo check | No `secrets.h`, token or server URL anywhere in the GitHub repo or its history |
| A10 | Server tests | `pytest` passes |

---

## 12. Known limitations and future work

- **Polling latency and traffic:** a 2 s poll adds up to 2 s of delay. Long-polling, a WebSocket or MQTT can replace it later; the protocol's generic `command` field was chosen to make that swap easier. **[Team: can change in the future]**
- **No persistence:** state resets on every deploy. A database (Railway Postgres) becomes necessary once ping history, reports or multiple users arrive.
- **Open dashboard:** login and per-user privileges come in a later iteration.
- **Blocking ping pattern:** fine for 1.5 s. Longer alert patterns should become non-blocking.
- **Only one board at a time:** routing a ping to a specific board would need a target field on the ping.
- **Option (a) for higher-current lights:** if the 5 mm LED is replaced by something drawing more than a pin can supply, switch PWM to a transistor or MOSFET. The firmware stays the same (one PWM pin, one relay pin).
- **Future direction:** the Ping becomes the "someone is trying to reach you" signal of the DND bypass alert light.

---

## 13. Decision log

| Decision | By | Date |
|---|---|---|
| Arduino Nano ESP32, 5 mm LED, SRD-05VDC-SL-C relay through PN2222 + 1N4007 | Tristan and Alex | 2026-11-22 |
| PWM directly from GPIO, relay in series as master switch (option b) | Tristan and Alex | 2026-11-22 |
| C++ Arduino sketch; arduino-cli and Arduino IDE both supported | Tristan | 2026-11-22 |
| Polling over HTTPS with certificate verification | Tristan | 2026-11-22 |
| Per-board token, one board active at a time | Tristan | 2026-11-22 |
| Ping = 3 quick fades about 1.5 s; boot status on onboard RGB only | Tristan | 2026-11-22 |
| Flask on Railway, one service, no database, no login, no public API | Tristan | 2026-11-22 |
| Public repo `engr491-smart-light` on Tristan's account | Tristan | 2026-11-22 |
| Pins, timing constants, endpoint shapes, single gunicorn worker | This design doc (changeable) | 2026-11-22 |
