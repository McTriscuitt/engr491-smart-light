// Wi-Fi connect/reconnect, time sync, HTTPS poll and ack (DESIGN.md 5.5, 5.7, 5.8).
#pragma once

#include <Arduino.h>

enum PollResult {
  POLL_NONE,          // {"command":"none"}
  POLL_PING,          // {"command":"ping","ping_id":...}
  POLL_UNAUTHORIZED,  // 401: token rejected
  POLL_ERROR,         // network, TLS, HTTP or parse error (already logged)
};

void netInit();                 // TLS client setup. Call once in setup()
void netWifiBegin();            // start (or restart) joining the network
bool netWifiConnected();
void netSyncTime();             // NTP, waits up to TIME_SYNC_TIMEOUT_MS
void netResetConnection();      // drop the kept-alive HTTPS connection

PollResult netPoll(String &pingId);
bool netAck(const String &pingId);
