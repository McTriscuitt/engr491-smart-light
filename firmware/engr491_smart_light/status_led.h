// Onboard RGB status patterns, non-blocking (DESIGN.md 5.5).
#pragma once

enum StatusPattern {
  STATUS_OFF,
  STATUS_BLINK_BLUE,   // connecting
  STATUS_SOLID_GREEN,  // connected (shown once)
  STATUS_SOLID_RED,    // Wi-Fi failed, waiting to retry
};

void statusLedInit();                      // all off
void statusLedSet(StatusPattern pattern);
void statusLedUpdate();                    // call every loop()
