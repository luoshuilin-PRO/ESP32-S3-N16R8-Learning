#include "macro_engine.h"
#include <string.h>
static void stop_action(macro_engine_t *s) {
    s->action=MAC_NORMAL; s->click=false; s->delta_y=0;
}
static void change_mode(macro_engine_t *s) {
    stop_action(s);
    s->blocked |= s->physical & MAC_LEFT;
}
void macro_engine_reset(macro_engine_t *s) {
    memset(s,0,sizeof(*s));
    s->need_neutral=true;
}
void macro_engine_input(macro_engine_t *s,uint8_t buttons,int64_t now_ms) {
    s->physical=buttons;
    s->blocked &= buttons;
    if(s->need_neutral) {
        if(buttons==0) s->need_neutral=false;
        return;
    }
    if((buttons & MAC_MIDDLE) && !s->middle_down) {
        s->middle_down=true; s->long_done=false; s->middle_at=now_ms;
    } else if(!(buttons & MAC_MIDDLE) && s->middle_down) {
        if(!s->long_done) {
            if(now_ms-s->middle_at<800) {
                s->enabled=!s->enabled; s->mode=MAC_NORMAL; change_mode(s);
            } else if(s->enabled) {
                s->mode=(s->mode+1)%3; change_mode(s);
            }
        }
        s->middle_down=false;
    }
}
void macro_engine_tick(macro_engine_t *s,int64_t now_ms,uint32_t random_value) {
    s->delta_y=0;
    if(s->need_neutral) { stop_action(s); return; }
    if(s->middle_down && !s->long_done && now_ms-s->middle_at>=800) {
        s->long_done=true;
        if(s->enabled) { s->mode=(s->mode+1)%3; change_mode(s); }
    }
    uint8_t desired=MAC_NORMAL;
    if(s->enabled && s->mode && (s->physical & MAC_LEFT) && !(s->blocked & MAC_LEFT))
        desired=s->mode;
    if(desired!=s->action) {
        stop_action(s); s->action=desired; s->deadline=now_ms;
        return; /* neutral transition before first macro press */
    }
    if(desired==MAC_NORMAL || now_ms<s->deadline) return;
    s->click=!s->click;
    unsigned delay;
    if(desired==MAC_MINIGUN)
        delay=s->click ? 140+random_value%16 : 20+random_value%11;
    else {
        delay=s->click ? 50 : 100;
        if(!s->click) s->delta_y=3;
    }
    s->deadline=now_ms+delay;
}
uint8_t macro_engine_buttons(const macro_engine_t *s) {
    uint8_t out=s->physical & (uint8_t)~MAC_MIDDLE & (uint8_t)~s->blocked;
    if(s->need_neutral) return 0;
    if(s->enabled && s->mode) out &= (uint8_t)~MAC_LEFT;
    if(s->click) out |= MAC_LEFT;
    return out;
}
