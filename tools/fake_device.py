"""Simulate a board against a local or deployed server (DESIGN.md 7).

    python tools/fake_device.py --url http://127.0.0.1:5000 --token <token> [--interval 2] [--pattern-seconds 1.5]

Polls /device/poll with the same body the firmware sends. On a ping it sleeps
for the pattern time, then acks (retrying once, like the board). Ctrl+C stops
it; the dashboard should show Offline about 6 s later.

The token is never printed. You can pass it with --token or the
FAKE_DEVICE_TOKEN environment variable (which keeps it out of shell history).
"""

import argparse
import os
import random
import sys
import time

import requests

FW_VERSION = "0.1.0-fake"
HTTP_TIMEOUT_S = 5


def stamp():
    return time.strftime("%H:%M:%S")


def post(session, url, body):
    return session.post(url, json=body, timeout=HTTP_TIMEOUT_S)


def ack(session, base, ping_id):
    body = {"ping_id": ping_id, "result": "ok"}
    for attempt in (1, 2):
        try:
            r = post(session, base + "/device/ack", body)
            print(f"{stamp()} ack {ping_id} -> {r.status_code} {r.text.strip()}")
            if r.ok:
                return
        except requests.RequestException as e:
            print(f"{stamp()} ack {ping_id} attempt {attempt} error: {e}")


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", required=True, help="server base URL, e.g. http://127.0.0.1:5000")
    p.add_argument("--token", default=os.environ.get("FAKE_DEVICE_TOKEN"),
                   help="device token (or set FAKE_DEVICE_TOKEN)")
    p.add_argument("--interval", type=float, default=2.0, help="seconds between polls")
    p.add_argument("--pattern-seconds", type=float, default=1.5, help="simulated light pattern time")
    p.add_argument("--auth-backoff", type=float, default=10.0, help="seconds to wait after a 401")
    args = p.parse_args()

    if not args.token:
        p.error("a token is required (--token or FAKE_DEVICE_TOKEN)")

    base = args.url.rstrip("/")
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {args.token}"
    print(f"{stamp()} fake device polling {base} every {args.interval:g} s (Ctrl+C to stop)")

    while True:
        wait = args.interval
        body = {"fw": FW_VERSION, "rssi": random.randint(-70, -45)}
        try:
            r = post(session, base + "/device/poll", body)
            if r.status_code == 401:
                print(f"{stamp()} poll -> 401 token rejected; backing off {args.auth_backoff:g} s")
                wait = args.auth_backoff
            elif not r.ok:
                print(f"{stamp()} poll -> {r.status_code} {r.text.strip()[:200]}")
            else:
                data = r.json()
                command = data.get("command")
                print(f"{stamp()} poll -> {r.status_code} {data}")
                if command == "ping":
                    print(f"{stamp()} running ping pattern ({args.pattern_seconds:g} s)")
                    time.sleep(args.pattern_seconds)
                    ack(session, base, data.get("ping_id"))
        except (requests.RequestException, ValueError) as e:
            print(f"{stamp()} poll error: {e}")
        time.sleep(wait)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped")
        sys.exit(0)
