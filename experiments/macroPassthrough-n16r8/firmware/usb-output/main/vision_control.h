#pragma once
#include <stdbool.h>
#include <stdint.h>
#define VISION_LEASE_MS 180
typedef struct { uint32_t seq; int64_t received_at; bool active; } vision_grant_t;
typedef struct {
    bool down, running, takeover_release;
    uint32_t resume_seq;
    int64_t deadline;
} vision_click_t;
uint32_t vision_crc(const uint8_t *p, unsigned n);
void vision_step(vision_click_t *s, vision_grant_t g, bool output_down, int64_t now);
uint8_t vision_buttons(const vision_click_t *s, uint8_t manual_buttons);
bool vision_needs_report(const vision_click_t *s);
void vision_sent(vision_click_t *s, int64_t now);
bool vision_fresh(vision_grant_t g, int64_t now);
void vision_uart_init(void);
vision_grant_t vision_get(void);
void vision_invalidate(void);
