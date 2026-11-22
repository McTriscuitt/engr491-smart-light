#include "status_led.h"

#include "config.h"

namespace {

StatusPattern current = STATUS_OFF;
uint32_t patternStart = 0;

// Active-low: LOW turns a colour on.
void writeRgb(bool red, bool green, bool blue) {
  digitalWrite(PIN_RGB_RED, red ? LOW : HIGH);
  digitalWrite(PIN_RGB_GREEN, green ? LOW : HIGH);
  digitalWrite(PIN_RGB_BLUE, blue ? LOW : HIGH);
}

}  // namespace

void statusLedInit() {
  // Set the level before switching to output so no colour flashes.
  digitalWrite(PIN_RGB_RED, HIGH);
  digitalWrite(PIN_RGB_GREEN, HIGH);
  digitalWrite(PIN_RGB_BLUE, HIGH);
  pinMode(PIN_RGB_RED, OUTPUT);
  pinMode(PIN_RGB_GREEN, OUTPUT);
  pinMode(PIN_RGB_BLUE, OUTPUT);
  writeRgb(false, false, false);
  current = STATUS_OFF;
}

void statusLedSet(StatusPattern pattern) {
  if (pattern == current) return;
  current = pattern;
  patternStart = millis();
  statusLedUpdate();
}

void statusLedUpdate() {
  switch (current) {
    case STATUS_OFF:
      writeRgb(false, false, false);
      break;
    case STATUS_BLINK_BLUE: {
      bool on = ((millis() - patternStart) / STATUS_BLINK_HALF_MS) % 2 == 0;
      writeRgb(false, false, on);
      break;
    }
    case STATUS_SOLID_GREEN:
      writeRgb(false, true, false);
      break;
    case STATUS_SOLID_RED:
      writeRgb(true, false, false);
      break;
  }
}
