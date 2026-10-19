#include "macro_engine.h"
#include <assert.h>
#include <stdio.h>
static void neutral(macro_engine_t *s) { macro_engine_reset(s); macro_engine_input(s,0,0); }
static void mode(macro_engine_t *s,unsigned target) {
    neutral(s);
    macro_engine_input(s,MAC_MIDDLE,10);
    macro_engine_input(s,0,20);
    assert(s->enabled && s->mode==0);
    for(unsigned i=0;i<target;i++) {
        int64_t t=1000+i*1000;
        macro_engine_input(s,MAC_MIDDLE,t);
        macro_engine_tick(s,t+800,0);
        macro_engine_input(s,0,t+801);
    }
    assert(s->mode==target);
}
int main(void) {
    macro_engine_t s;
    neutral(&s);
    macro_engine_input(&s,MAC_LEFT|MAC_RIGHT,1);
    assert(macro_engine_buttons(&s)==(MAC_LEFT|MAC_RIGHT));
    mode(&s,MAC_MINIGUN);
    macro_engine_input(&s,MAC_LEFT|MAC_RIGHT,2000);
    macro_engine_tick(&s,2000,0);
    assert(!(macro_engine_buttons(&s)&MAC_LEFT));
    macro_engine_tick(&s,2001,15);
    assert((macro_engine_buttons(&s)&(MAC_LEFT|MAC_RIGHT))==(MAC_LEFT|MAC_RIGHT));
    assert(s.deadline==2156);
    macro_engine_tick(&s,2156,10);
    assert((macro_engine_buttons(&s)&MAC_LEFT)==0 && s.deadline==2186);
    macro_engine_input(&s,MAC_RIGHT,2160);
    macro_engine_tick(&s,2160,0);
    assert(macro_engine_buttons(&s)==MAC_RIGHT);
    mode(&s,MAC_M4);
    macro_engine_input(&s,MAC_LEFT,4000);
    macro_engine_tick(&s,4000,0);
    macro_engine_tick(&s,4001,0);
    assert(s.click && s.deadline==4051);
    macro_engine_tick(&s,4051,0);
    assert(!s.click && s.delta_y==3 && s.deadline==4151);
    /* Switching modes while left is held requires a fresh release. */
    macro_engine_input(&s,MAC_MIDDLE|MAC_LEFT,4060);
    macro_engine_tick(&s,4860,0);
    assert(s.mode==MAC_NORMAL && !s.click);
    macro_engine_input(&s,MAC_LEFT,4861);
    assert((macro_engine_buttons(&s)&MAC_LEFT)==0);
    macro_engine_input(&s,0,4862);
    assert(macro_engine_buttons(&s)==0);
    macro_engine_reset(&s);
    macro_engine_input(&s,MAC_LEFT,5000);
    assert(macro_engine_buttons(&s)==0);
    macro_engine_input(&s,0,5001);
    macro_engine_input(&s,MAC_LEFT,5002);
    assert(macro_engine_buttons(&s)==MAC_LEFT);
    puts("PASS: macro engine prototype");
    return 0;
}
