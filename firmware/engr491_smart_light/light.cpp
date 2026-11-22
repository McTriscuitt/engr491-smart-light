#include "light.h"

#include "config.h"

// LEDC API: the installed core is arduino:esp32 2.0.18-arduino.5 (ESP32 Arduino
// core 2.x), which uses ledcSetup/ledcAttachPin and ledcWrite(channel, duty).
// Core 3.x would use ledcAttach(pin, freq, bits) and ledcWrite(pin, duty).
// Only this file needs to change if the core is upgraded.

void lightInit() {
  // Relay off before anything else: set the level, then make it an output.
  digitalWrite(PIN_RELAY, LOW);
  pinMode(PIN_RELAY, OUTPUT);
  digitalWrite(PIN_RELAY, LOW);

  ledcSetup(PWM_CHANNEL, PWM_FREQ_HZ, PWM_RES_BITS);
  ledcAttachPin(PIN_LED_PWM, PWM_CHANNEL);
  lightSetDuty(0);
}

void lightSetDuty(uint8_t duty) {
  ledcWrite(PWM_CHANNEL, duty);
}

void lightSetRelay(bool on) {
  digitalWrite(PIN_RELAY, on ? HIGH : LOW);
}

namespace {

// Simple perceptual curve so the fade doesn't look bright most of the way.
uint8_t perceptual(uint8_t linear) {
  return static_cast<uint8_t>((static_cast<uint16_t>(linear) * linear) / 255);
}

void fade(bool up) {
  const uint32_t stepMs = PING_HALF_CYCLE_MS / PING_FADE_STEPS;
  for (uint8_t i = 0; i <= PING_FADE_STEPS; i++) {
    uint8_t step = up ? i : PING_FADE_STEPS - i;
    uint8_t linear = static_cast<uint8_t>((static_cast<uint16_t>(step) * 255) / PING_FADE_STEPS);
    lightSetDuty(perceptual(linear));
    delay(stepMs);
  }
}

}  // namespace

void lightRunPingPattern() {
  lightSetDuty(0);
  lightSetRelay(true);
  delay(RELAY_SETTLE_MS);

  for (uint8_t cycle = 0; cycle < PING_CYCLES; cycle++) {
    fade(true);
    fade(false);
  }

  lightSetDuty(0);
  lightSetRelay(false);
}
