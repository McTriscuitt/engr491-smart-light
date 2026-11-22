// engr491-smart-light firmware, iteration 1 (DESIGN.md Section 5).
//
// Arduino Nano ESP32 polls the server over HTTPS. On a ping it closes the relay,
// fades the 5 mm LED up and down 3 times (~1.5 s), opens the relay and acks.
//
// Wi-Fi states (onboard RGB):
//   CONNECTING       blue blinking      -> CONNECTED_FLASH, or WIFI_FAILED on timeout
//   CONNECTED_FLASH  green ~500 ms      -> RUNNING
//   WIFI_FAILED      red                -> CONNECTING after WIFI_RETRY_DELAY_MS
//   RUNNING          off                -> CONNECTING if Wi-Fi drops

#include <WiFi.h>

#include "config.h"
#include "light.h"
#include "net.h"
#include "status_led.h"

enum WifiState { CONNECTING, CONNECTED_FLASH, WIFI_FAILED, RUNNING };

static WifiState state = CONNECTING;
static uint32_t stateSince = 0;
static uint32_t lastPollAt = 0;
static uint32_t pollWaitMs = 0;  // 0 = poll right away
static bool timeSynced = false;

static void enterState(WifiState next) {
  state = next;
  stateSince = millis();
  switch (next) {
    case CONNECTING:
      statusLedSet(STATUS_BLINK_BLUE);
      netResetConnection();
      netWifiBegin();
      break;
    case CONNECTED_FLASH:
      statusLedSet(STATUS_SOLID_GREEN);
      Serial.printf("[wifi] connected, IP %s, RSSI %d dBm\n",
                    WiFi.localIP().toString().c_str(), WiFi.RSSI());
      break;
    case WIFI_FAILED:
      statusLedSet(STATUS_SOLID_RED);
      Serial.printf("[wifi] failed to connect; retrying in %lu s\n",
                    (unsigned long)(WIFI_RETRY_DELAY_MS / 1000));
      WiFi.disconnect();
      break;
    case RUNNING:
      statusLedSet(STATUS_OFF);
      if (!timeSynced) {
        netSyncTime();
        timeSynced = true;
      }
      pollWaitMs = 0;
      break;
  }
}

static void handlePing(const String &pingId) {
  Serial.printf("[ping] %s: running pattern\n", pingId.c_str());
  lightRunPingPattern();
  if (netAck(pingId)) {
    Serial.printf("[ping] %s: acked\n", pingId.c_str());
  } else if (netAck(pingId)) {  // retry once
    Serial.printf("[ping] %s: acked on retry\n", pingId.c_str());
  } else {
    Serial.printf("[ping] %s: ack failed\n", pingId.c_str());
  }
}

static void runPoll() {
  lastPollAt = millis();
  pollWaitMs = POLL_INTERVAL_MS;

  String pingId;
  switch (netPoll(pingId)) {
    case POLL_NONE:
      break;
    case POLL_PING:
      handlePing(pingId);
      break;
    case POLL_UNAUTHORIZED:
      Serial.printf("[poll] token rejected (401); backing off %lu s\n",
                    (unsigned long)(AUTH_FAIL_BACKOFF_MS / 1000));
      pollWaitMs = AUTH_FAIL_BACKOFF_MS;
      break;
    case POLL_ERROR:
      break;  // already logged; keep polling at the normal interval
  }
}

void setup() {
  // The 5 mm LED must never light at boot: relay off and PWM at 0 first.
  lightInit();
  statusLedInit();
  Serial.begin(115200);
  delay(200);

  Serial.printf("\n[boot] engr491-smart-light fw %s\n", FW_VERSION);
#if !TLS_VERIFY
  for (int i = 0; i < 3; i++) {
    Serial.println("[boot] !!!!! WARNING: TLS_VERIFY is 0. The server certificate is NOT verified. !!!!!");
  }
#endif

  netInit();
  enterState(CONNECTING);
}

void loop() {
  statusLedUpdate();
  uint32_t now = millis();

  switch (state) {
    case CONNECTING:
      if (netWifiConnected()) {
        enterState(CONNECTED_FLASH);
      } else if (now - stateSince >= WIFI_CONNECT_TIMEOUT_MS) {
        enterState(WIFI_FAILED);
      }
      break;

    case CONNECTED_FLASH:
      if (now - stateSince >= CONNECTED_FLASH_MS) enterState(RUNNING);
      break;

    case WIFI_FAILED:
      if (now - stateSince >= WIFI_RETRY_DELAY_MS) enterState(CONNECTING);
      break;

    case RUNNING:
      if (!netWifiConnected()) {
        Serial.println("[wifi] lost connection");
        enterState(CONNECTING);
      } else if (now - lastPollAt >= pollWaitMs) {
        runPoll();
      }
      break;
  }

  delay(10);
}
