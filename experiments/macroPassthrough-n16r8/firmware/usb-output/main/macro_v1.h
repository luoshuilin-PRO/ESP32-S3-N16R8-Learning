#pragma once
#include <stdbool.h>
#include <stdint.h>

enum { V1_LEFT = 1, V1_RIGHT = 2, V1_MIDDLE = 4, V1_BACK = 8, V1_FORWARD = 16 };
enum { V1_IDLE, V1_MINIGUN, V1_M4 };
typedef struct {
    bool enabled, middle_down, long_done, click, ctrl, space, left_suspended;
    uint8_t mode, physical, blocked, action, phase;
    int64_t middle_at, deadline, led_epoch;
    int8_t recoil;
} macro_v1_t;

void macro_v1_reset(macro_v1_t *s);
void macro_v1_input(macro_v1_t *s, uint8_t buttons, int64_t now);
void macro_v1_tick(macro_v1_t *s, int64_t now, uint32_t random);
uint8_t macro_v1_buttons(const macro_v1_t *s);
bool macro_v1_led(const macro_v1_t *s, int64_t now);
