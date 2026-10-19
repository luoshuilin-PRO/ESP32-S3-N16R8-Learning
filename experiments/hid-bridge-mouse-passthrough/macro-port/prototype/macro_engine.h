#ifndef MACRO_ENGINE_H
#define MACRO_ENGINE_H
#include <stdbool.h>
#include <stdint.h>
enum { MAC_LEFT=1, MAC_RIGHT=2, MAC_MIDDLE=4, MAC_BACK=8, MAC_FORWARD=16 };
enum { MAC_NORMAL=0, MAC_MINIGUN=1, MAC_M4=2 };
typedef struct {
    bool enabled, middle_down, long_done, click, need_neutral;
    uint8_t mode, physical, blocked, action;
    int64_t middle_at, deadline;
    int8_t delta_y;
} macro_engine_t;
void macro_engine_reset(macro_engine_t *s);
void macro_engine_input(macro_engine_t *s, uint8_t buttons, int64_t now_ms);
void macro_engine_tick(macro_engine_t *s, int64_t now_ms, uint32_t random_value);
uint8_t macro_engine_buttons(const macro_engine_t *s);
#endif
