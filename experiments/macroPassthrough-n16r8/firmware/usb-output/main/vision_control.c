#include "vision_control.h"
#include <limits.h>
uint32_t vision_crc(const uint8_t *p, unsigned n)
{
    uint32_t c = 0xffffffff;
    while (n--) {
        c ^= *p++;
        for (unsigned i = 0; i < 8; ++i)
            c = (c >> 1) ^ (0xedb88320U & (0U - (c & 1)));
    }
    return ~c;
}
bool vision_fresh(vision_grant_t g, int64_t now)
{
    return g.active && now >= g.received_at && now - g.received_at < VISION_LEASE_MS;
}
void vision_step(vision_click_t *s, vision_grant_t g, bool output_down, int64_t now)
{
    if (!vision_fresh(g, now)) {
        s->down = s->running = false;
        s->takeover_release = false;
        s->resume_seq = g.seq;
        // Loss of detection cancels immediately, without delaying the next new hit.
        s->deadline = 0;
        return;
    }
    if (!s->running) {
        if (g.seq == s->resume_seq) return;
        s->running = true;
        // A physical/macro press already on USB must be released before a new click.
        s->takeover_release = output_down;
        s->down = !output_down;
        s->deadline = INT64_MAX;
    } else if (now >= s->deadline) {
        s->down = !s->down;
        s->deadline = INT64_MAX;
    }
}
void vision_sent(vision_click_t *s, int64_t now)
{
    if (vision_needs_report(s)) {
        s->deadline = now + (s->takeover_release ? 5 : (s->down ? 50 : 100));
        s->takeover_release = false;
    }
}

bool vision_needs_report(const vision_click_t *s)
{
    return s->running && s->deadline == INT64_MAX;
}

uint8_t vision_buttons(const vision_click_t *s, uint8_t manual_buttons)
{
    if (!s->running) return manual_buttons;
    return (manual_buttons & ~1U) | (s->down ? 1U : 0U);
}
