// Pins, timing constants and firmware version (DESIGN.md 4.2, 5.4). Committed.
// Pins belong to Alex: if the circuit uses different pins, change them here only.
#pragma once

#include <Arduino.h>

#define FW_VERSION "0.1.0"

// --- Pins (Arduino pin names; work with either "Pin Numbering" menu setting) ---
constexpr uint8_t PIN_LED_PWM = D3;  // GPIO6: series resistor -> relay COM/NO -> 5 mm LED
constexpr uint8_t PIN_RELAY   = D2;  // GPIO5: PN2222 base resistor. HIGH = relay energized

// Onboard RGB LED, active-low (LOW = on). Some early boards have green and blue
// swapped; if the "connecting" blink shows green, swap these two lines.
constexpr uint8_t PIN_RGB_RED   = LED_RED;
constexpr uint8_t PIN_RGB_GREEN = LED_GREEN;
constexpr uint8_t PIN_RGB_BLUE  = LED_BLUE;

// --- PWM (LEDC) ---
constexpr uint8_t  PWM_CHANNEL  = 0;
constexpr uint32_t PWM_FREQ_HZ  = 5000;  // flicker-free for an LED
constexpr uint8_t  PWM_RES_BITS = 8;     // duty 0 to 255

// --- Ping pattern (R9) ---
constexpr uint8_t  PING_CYCLES        = 3;
constexpr uint32_t PING_HALF_CYCLE_MS = 250;  // fade up 250 ms, fade down 250 ms
constexpr uint8_t  PING_FADE_STEPS    = 50;   // ~5 ms per step
constexpr uint32_t RELAY_SETTLE_MS    = 20;   // relay operate time is under 10 ms

// --- Status LED ---
constexpr uint32_t STATUS_BLINK_HALF_MS  = 250;  // blue blink at ~2 Hz
constexpr uint32_t CONNECTED_FLASH_MS    = 500;  // green once

// --- Network ---
constexpr uint32_t POLL_INTERVAL_MS        = 2000;   // R7
constexpr uint32_t HTTP_TIMEOUT_MS         = 5000;   // per request
constexpr uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000;  // before showing red
constexpr uint32_t WIFI_RETRY_DELAY_MS     = 5000;   // red shown during this wait
constexpr uint32_t AUTH_FAIL_BACKOFF_MS    = 10000;  // poll slower after a 401
constexpr uint32_t TIME_SYNC_TIMEOUT_MS    = 10000;

// 1 = verify the server certificate against root_ca.h (default).
// 0 = last-resort fallback only (DESIGN.md 5.8): the board prints a loud warning.
#define TLS_VERIFY 1
