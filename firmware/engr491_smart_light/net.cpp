#include "net.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <time.h>

#include "config.h"
#include "root_ca.h"

#if !__has_include("secrets.h")
#error "secrets.h is missing: copy secrets.example.h to secrets.h in this folder and fill it in"
#endif
#include "secrets.h"

// Never print DEVICE_TOKEN or WIFI_PASSWORD.

namespace {

WiFiClientSecure tls;  // kept alive across polls so each poll skips the TLS handshake
HTTPClient http;

const char *wifiStatusName(wl_status_t s) {
  switch (s) {
    case WL_IDLE_STATUS: return "idle";
    case WL_NO_SSID_AVAIL: return "network not found";
    case WL_CONNECTED: return "connected";
    case WL_CONNECT_FAILED: return "connect failed";
    case WL_CONNECTION_LOST: return "connection lost";
    case WL_DISCONNECTED: return "disconnected";
    default: return "unknown";
  }
}

// POST a JSON body. Returns the HTTP status (negative for transport errors)
// and fills `response` on success.
int postJson(const char *path, const String &body, String &response) {
  if (!http.begin(tls, SERVER_HOST, 443, path, true)) {
    Serial.printf("[net] %s: begin failed\n", path);
    return -1;
  }
  http.setReuse(true);
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
  http.addHeader("Content-Type", "application/json");

  int code = http.POST(body);
  if (code > 0) {
    response = http.getString();
  } else {
    Serial.printf("[net] %s: %s\n", path, HTTPClient::errorToString(code).c_str());
  }
  http.end();  // keeps the connection open for reuse when the server allows it

  if (code <= 0) {
    netResetConnection();  // reconnect cleanly on the next request
  }
  return code;
}

}  // namespace

void netInit() {
#if TLS_VERIFY
  tls.setCACert(ROOT_CA_PEM);
#else
  tls.setInsecure();
#endif
  tls.setHandshakeTimeout(HTTP_TIMEOUT_MS / 1000);
}

void netWifiBegin() {
  WiFi.disconnect();
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(false);  // the state machine in the .ino owns reconnection
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.printf("[wifi] connecting to \"%s\"\n", WIFI_SSID);
}

bool netWifiConnected() {
  wl_status_t s = WiFi.status();
  static wl_status_t last = WL_IDLE_STATUS;
  if (s != last) {
    Serial.printf("[wifi] status: %s\n", wifiStatusName(s));
    last = s;
  }
  return s == WL_CONNECTED;
}

void netSyncTime() {
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
  Serial.print("[time] syncing");
  uint32_t start = millis();
  while (time(nullptr) < 1700000000 && millis() - start < TIME_SYNC_TIMEOUT_MS) {
    delay(250);
    Serial.print(".");
  }
  time_t now = time(nullptr);
  if (now >= 1700000000) {
    struct tm utc;
    gmtime_r(&now, &utc);
    char buf[32];
    strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S UTC", &utc);
    Serial.printf(" ok: %s\n", buf);
  } else {
    Serial.println(" timed out (continuing; TLS may fail if it checks dates)");
  }
}

void netResetConnection() {
  tls.stop();
}

PollResult netPoll(String &pingId) {
  JsonDocument req;
  req["fw"] = FW_VERSION;
  req["rssi"] = WiFi.RSSI();
  String body;
  serializeJson(req, body);

  String response;
  int code = postJson("/device/poll", body, response);
  if (code == 401) return POLL_UNAUTHORIZED;
  if (code != 200) {
    if (code > 0) Serial.printf("[poll] HTTP %d\n", code);
    return POLL_ERROR;
  }

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, response);
  if (err) {
    Serial.printf("[poll] bad JSON: %s\n", err.c_str());
    return POLL_ERROR;
  }

  const char *command = doc["command"] | "";
  if (strcmp(command, "ping") == 0) {
    pingId = doc["ping_id"] | "";
    if (pingId.isEmpty()) {
      Serial.println("[poll] ping without ping_id");
      return POLL_ERROR;
    }
    return POLL_PING;
  }
  if (strcmp(command, "none") != 0) {
    Serial.printf("[poll] unknown command \"%s\", ignoring\n", command);
  }
  return POLL_NONE;
}

bool netAck(const String &pingId) {
  JsonDocument req;
  req["ping_id"] = pingId;
  req["result"] = "ok";
  String body;
  serializeJson(req, body);

  String response;
  int code = postJson("/device/ack", body, response);
  if (code == 200) return true;
  if (code > 0) Serial.printf("[ack] HTTP %d %s\n", code, response.c_str());
  return false;
}
