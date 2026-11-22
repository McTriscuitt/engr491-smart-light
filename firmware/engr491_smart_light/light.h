// Relay + PWM control and the ping pattern (DESIGN.md 5.5, 5.6).
#pragma once

#include <stdint.h>

void lightInit();                 // relay off, PWM attached at duty 0. Call first in setup()
void lightSetDuty(uint8_t duty);  // 0 to 255
void lightSetRelay(bool on);
void lightRunPingPattern();       // blocking, about 1.5 s
