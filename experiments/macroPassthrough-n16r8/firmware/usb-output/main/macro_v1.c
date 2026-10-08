#include "macro_v1.h"

static void cancel(macro_v1_t *s)
{
    s->action = V1_IDLE;
    s->click = s->ctrl = s->space = false;
    s->phase = 0;
    s->recoil = 0;
}

static void change_mode(macro_v1_t *s, int64_t now)
{
    cancel(s);
    // Require release before a held trigger can start another action.
    s->blocked |= s->physical & V1_LEFT;
    s->led_epoch = now;
}

void macro_v1_reset(macro_v1_t *s)
{
    *s = (macro_v1_t){0};
}

void macro_v1_input(macro_v1_t *s, uint8_t buttons, int64_t now)
{
    s->physical = buttons;
    s->blocked &= buttons;
    if ((buttons & V1_MIDDLE) && !s->middle_down) {
        s->middle_down = true;
        s->long_done = false;
        s->middle_at = now;
    } else if (!(buttons & V1_MIDDLE) && s->middle_down) {
        if (!s->long_done) {
            if (now - s->middle_at < 800) {
                s->enabled = !s->enabled;
                s->mode = 0;
                change_mode(s, now);
            } else if (s->enabled) {
                s->mode = (s->mode + 1) % 3;
                change_mode(s, now);
            }
        }
        s->middle_down = false;
    }
}

void macro_v1_tick(macro_v1_t *s, int64_t now, uint32_t random)
{
    s->recoil = 0;
    if (s->middle_down && !s->long_done && now - s->middle_at >= 800) {
        s->long_done = true;
        if (s->enabled) {
            s->mode = (s->mode + 1) % 3;
            change_mode(s, now);
        }
    }
    uint8_t desired = V1_IDLE;
    uint8_t available = s->physical & ~s->blocked;
    if (s->enabled && s->mode && !s->left_suspended) {
        if (available & V1_LEFT) desired = s->mode == 1 ? V1_MINIGUN : V1_M4;
    }
    if (desired != s->action) {
        cancel(s);
        s->action = desired;
        s->deadline = now;
        s->led_epoch = now;
        // Send a neutral transition before starting the replacement action.
        return;
    }
    if (s->action == V1_IDLE || now < s->deadline) return;
    unsigned delay;
    {
        s->click = !s->click;
        if (s->action == V1_MINIGUN) delay = s->click ? 140 + random % 16 : 20 + random % 11;
        else {
            delay = s->click ? 50 : 100;
            if (!s->click) s->recoil = 3;
        }
    }
    // Do not replay missed edges in a burst after a USB stall.
    s->deadline = now + delay;
}

uint8_t macro_v1_buttons(const macro_v1_t *s)
{
    uint8_t buttons = s->physical & ~V1_MIDDLE & ~s->blocked;
    if (s->enabled) buttons &= ~(V1_BACK | V1_FORWARD);
    if (s->enabled && s->mode) buttons &= ~V1_LEFT;
    if (s->click) buttons |= V1_LEFT;
    return buttons;
}

bool macro_v1_led(const macro_v1_t *s, int64_t now)
{
    if (!s->enabled || !s->mode) return false;
    unsigned period = s->mode == 1 ? 500 : 2000;
    return ((now - s->led_epoch) / period) % 2 == 0;
}
