#include "macro_v1.h"
#include "vision_control.h"
#include "esp_log.h"
#include "esp_check.h"
#define CHECK(expr) do { if (!(expr)) { ESP_LOGE("macro_test", "line %d: %s", __LINE__, #expr); return ESP_FAIL; } ++checks; } while (0)
esp_err_t macro_v1_selftest(void)
{
    unsigned checks = 0;
    macro_v1_t s;
    macro_v1_reset(&s);
    CHECK(!s.enabled && !macro_v1_led(&s, 0));
    macro_v1_input(&s, V1_MIDDLE, 0);
    macro_v1_input(&s, 0, 100);
    CHECK(s.enabled && s.mode == 0);
    macro_v1_input(&s, V1_MIDDLE, 200);
    macro_v1_tick(&s, 1000, 0);
    macro_v1_input(&s, 0, 1001);
    CHECK(s.mode == 1);
    CHECK(macro_v1_led(&s, 1000) && !macro_v1_led(&s, 1500));
    macro_v1_input(&s, V1_MIDDLE, 1100);
    macro_v1_tick(&s, 1900, 0);
    macro_v1_input(&s, 0, 1901);
    CHECK(s.mode == 2 && macro_v1_led(&s, 1900) && !macro_v1_led(&s, 3900));
    macro_v1_input(&s, V1_MIDDLE, 2000);
    macro_v1_tick(&s, 2800, 0);
    macro_v1_input(&s, 0, 2801);
    CHECK(s.mode == 0);
    macro_v1_input(&s, V1_MIDDLE, 2900);
    macro_v1_input(&s, 0, 2950);
    CHECK(!s.enabled);
    for (unsigned mode = 0; mode <= 2; ++mode) {
        macro_v1_reset(&s); s.enabled = true; s.mode = mode;
        macro_v1_input(&s, V1_RIGHT, 0);
        macro_v1_tick(&s, 0, 0); macro_v1_tick(&s, 1, 0);
        CHECK(macro_v1_buttons(&s) == V1_RIGHT && s.action == V1_IDLE);
        macro_v1_input(&s, V1_RIGHT | V1_LEFT, 10);
        macro_v1_tick(&s, 10, 0); macro_v1_tick(&s, 11, 0);
        CHECK((macro_v1_buttons(&s) & V1_RIGHT) != 0);
        CHECK((macro_v1_buttons(&s) & V1_LEFT) != 0);
        if (mode) {
            CHECK(s.deadline == 11 + (mode == 1 ? 140 : 50));
            macro_v1_tick(&s, s.deadline, 0);
            CHECK(!s.click && s.recoil == (mode == 2 ? 3 : 0));
        }
        macro_v1_input(&s, 0, 1000); macro_v1_tick(&s, 1000, 0);
        CHECK(!s.click && !s.ctrl && !s.space);
        macro_v1_input(&s, V1_BACK, 1001); macro_v1_tick(&s, 1001, 0);
        CHECK(s.action == V1_IDLE && !s.ctrl && !s.space);
    }
    vision_click_t v = {0};
    vision_grant_t g = {1, 0, true};
    CHECK(vision_fresh(g, 179) && !vision_fresh(g, 180));
    vision_step(&v, g, false, 0); CHECK(v.down);
    vision_sent(&v, 10); CHECK(v.deadline == 60);
    vision_step(&v, g, false, 60); CHECK(!v.down);
    vision_sent(&v, 60); CHECK(v.deadline == 160);
    vision_step(&v, g, false, 160); CHECK(v.down);
    // A held physical left must not cancel a running vision click.
    vision_step(&v, g, true, 161); CHECK(v.down && v.running);
    CHECK(vision_buttons(&v, V1_LEFT | V1_RIGHT) == (V1_LEFT | V1_RIGHT));
    g = (vision_grant_t){2, 263, true};
    vision_step(&v, g, false, 263); CHECK(v.down);
    g.active = false;
    vision_step(&v, g, false, 264); CHECK(!v.down && !v.running);
    g = (vision_grant_t){3, 400, true};
    vision_step(&v, g, false, 400); CHECK(v.down);
    vision_step(&v, g, false, 580); CHECK(!v.down);
    // Idle frames must not continually push the first click into the future.
    v = (vision_click_t){0};
    g = (vision_grant_t){10, 1000, false};
    vision_step(&v, g, false, 1000);
    vision_step(&v, g, false, 1050);
    CHECK(!v.down && !v.running && v.deadline == 0);
    g = (vision_grant_t){11, 1051, true};
    vision_step(&v, g, false, 1051); CHECK(v.down);
    vision_sent(&v, 1052); CHECK(v.deadline == 1102);
    g.active = false;
    vision_step(&v, g, false, 1060); CHECK(!v.down);
    g = (vision_grant_t){12, 1061, true};
    vision_step(&v, g, false, 1061); CHECK(v.down);
    vision_sent(&v, 1062);
    vision_step(&v, g, false, 1112); CHECK(!v.down);
    vision_sent(&v, 1113); CHECK(v.deadline == 1213);
    g = (vision_grant_t){13, 1212, true};
    vision_step(&v, g, false, 1212); CHECK(!v.down);
    vision_step(&v, g, false, 1213); CHECK(v.down);
    // Takeover of an already-down USB left emits a release before the first press.
    v = (vision_click_t){0};
    g = (vision_grant_t){20, 2000, true};
    vision_step(&v, g, true, 2000);
    CHECK(v.running && !v.down && v.takeover_release && vision_needs_report(&v));
    CHECK(vision_buttons(&v, V1_LEFT | V1_RIGHT) == V1_RIGHT);
    vision_sent(&v, 2001); CHECK(v.deadline == 2006 && !v.takeover_release);
    vision_step(&v, g, true, 2005); CHECK(!v.down);
    vision_step(&v, g, true, 2006); CHECK(v.down);
    vision_sent(&v, 2007); CHECK(v.deadline == 2057);
    vision_step(&v, g, true, 2057); CHECK(!v.down);
    CHECK(vision_buttons(&v, V1_LEFT | V1_RIGHT) == V1_RIGHT);
    vision_sent(&v, 2058); CHECK(v.deadline == 2158);
    g.active = false;
    vision_step(&v, g, true, 2060); CHECK(!v.down && !v.running);
    CHECK(vision_buttons(&v, V1_LEFT | V1_RIGHT) == (V1_LEFT | V1_RIGHT));
    CHECK(vision_buttons(&v, V1_RIGHT) == V1_RIGHT);
    g = (vision_grant_t){21, 2061, true};
    vision_step(&v, g, false, 2061); CHECK(v.down);
    vision_step(&v, g, true, 2241); CHECK(!v.running && !v.down);
    CHECK(vision_buttons(&v, V1_RIGHT) == V1_RIGHT);
    // Suspend both macro engines without losing physical buttons or mode selection.
    for (unsigned mode = 0; mode <= 2; ++mode) {
        macro_v1_reset(&s); s.enabled = true; s.mode = mode;
        macro_v1_input(&s, V1_LEFT | V1_RIGHT, 3000);
        macro_v1_tick(&s, 3000, 0); macro_v1_tick(&s, 3001, 0);
        v = (vision_click_t){0}; g = (vision_grant_t){30, 3002, true};
        vision_step(&v, g, true, 3002);
        s.left_suspended = v.running;
        macro_v1_tick(&s, 3002, 0);
        CHECK(s.action == V1_IDLE && !s.click && !s.recoil && s.mode == mode);
        CHECK(s.physical == (V1_LEFT | V1_RIGHT));
        CHECK(vision_buttons(&v, macro_v1_buttons(&s)) == V1_RIGHT);
        vision_sent(&v, 3003);
        vision_step(&v, g, false, 3008);
        macro_v1_tick(&s, 3008, 0);
        CHECK(vision_buttons(&v, macro_v1_buttons(&s)) == (V1_LEFT | V1_RIGHT));
        CHECK(!s.recoil && s.action == V1_IDLE);
        g.active = false;
        vision_step(&v, g, true, 3010); s.left_suspended = v.running;
        macro_v1_tick(&s, 3010, 0); macro_v1_tick(&s, 3011, 0);
        CHECK(vision_buttons(&v, macro_v1_buttons(&s)) == (V1_LEFT | V1_RIGHT));
        CHECK(s.action == (mode == 0 ? V1_IDLE : (mode == 1 ? V1_MINIGUN : V1_M4)));
        macro_v1_input(&s, V1_RIGHT, 3012); macro_v1_tick(&s, 3012, 0);
        CHECK(vision_buttons(&v, macro_v1_buttons(&s)) == V1_RIGHT);
    }
    CHECK(vision_crc((const uint8_t *)"123456789", 9) == 0xcbf43926);
    ESP_LOGI("macro_test", "PASS: %u macro/vision checks", checks);
    return ESP_OK;
}
