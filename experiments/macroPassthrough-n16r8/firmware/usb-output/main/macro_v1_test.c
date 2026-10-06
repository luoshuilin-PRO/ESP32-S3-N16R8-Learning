#include "macro_v1.h"
#include "esp_log.h"
#include "esp_check.h"

#define CHECK(expr) do { if (!(expr)) { \
    ESP_LOGE("macro_test", "line %d: %s", __LINE__, #expr); \
    return ESP_FAIL; } ++checks; } while (0)

esp_err_t macro_v1_selftest(void)
{
    unsigned checks = 0;
    macro_v1_t s;
    macro_v1_reset(&s);
    CHECK(!s.enabled && !macro_v1_led(&s, 0));
    macro_v1_input(&s, V1_LEFT | V1_FORWARD | V1_BACK, 0);
    CHECK(macro_v1_buttons(&s) == (V1_LEFT | V1_FORWARD | V1_BACK));
    macro_v1_input(&s, V1_MIDDLE, 10);
    macro_v1_input(&s, 0, 100);
    CHECK(s.enabled && s.mode == 0);
    macro_v1_input(&s, V1_BACK | V1_FORWARD | V1_LEFT, 110);
    macro_v1_tick(&s, 110, 0);
    CHECK(s.action == V1_IDLE && macro_v1_buttons(&s) == V1_LEFT);
    CHECK(!macro_v1_led(&s, 110));
    macro_v1_input(&s, V1_MIDDLE, 200);
    macro_v1_tick(&s, 1000, 0);
    CHECK(s.mode == 1 && s.enabled);
    CHECK(macro_v1_led(&s, 1000) && !macro_v1_led(&s, 1500));
    macro_v1_input(&s, 0, 1001);
    CHECK(s.mode == 1 && s.enabled);
    macro_v1_input(&s, V1_LEFT, 1100);
    macro_v1_tick(&s, 1100, 0);
    macro_v1_tick(&s, 1101, 0);
    CHECK(s.action == V1_MINIGUN && s.click && s.deadline == 1241);
    macro_v1_tick(&s, 1240, 0);
    CHECK(s.click);
    macro_v1_tick(&s, 1241, 0);
    CHECK(!s.click && s.deadline == 1261);
    macro_v1_input(&s, 0, 1242);
    macro_v1_tick(&s, 1242, 0);
    CHECK(s.action == V1_IDLE && !s.click);
    macro_v1_input(&s, V1_MIDDLE, 1300);
    macro_v1_tick(&s, 2100, 0);
    macro_v1_input(&s, 0, 2101);
    CHECK(s.mode == 2);
    CHECK(macro_v1_led(&s, 2100) && !macro_v1_led(&s, 4100));
    macro_v1_input(&s, V1_LEFT, 2200);
    macro_v1_tick(&s, 2200, 0);
    macro_v1_tick(&s, 2201, 0);
    CHECK(s.click && s.deadline == 2251);
    macro_v1_tick(&s, 2251, 0);
    CHECK(!s.click && s.recoil == 3 && s.deadline == 2351);
    macro_v1_tick(&s, 2252, 0);
    CHECK(s.recoil == 0);
    macro_v1_input(&s, V1_RIGHT | V1_LEFT, 2260);
    macro_v1_tick(&s, 2260, 0);
    macro_v1_tick(&s, 2261, 0);
    CHECK(s.action == V1_USP && s.click && s.deadline == 2299);
    macro_v1_tick(&s, 2299, 0);
    CHECK(!s.click && s.deadline == 2304);
    CHECK(macro_v1_led(&s, 2260) && !macro_v1_led(&s, 2360));
    macro_v1_input(&s, V1_LEFT, 2300);
    macro_v1_tick(&s, 2300, 0);
    CHECK(s.action == V1_IDLE && !s.click && (s.blocked & V1_LEFT));
    macro_v1_tick(&s, 2500, 0);
    CHECK(s.action == V1_IDLE && !macro_v1_buttons(&s));
    macro_v1_input(&s, 0, 2501);
    macro_v1_input(&s, V1_BACK, 2510);
    macro_v1_tick(&s, 2510, 0);
    macro_v1_tick(&s, 2511, 0);
    CHECK(s.action == V1_GHOST && s.space && !s.ctrl);
    macro_v1_tick(&s, 2521, 0);
    CHECK(!s.space && !s.ctrl);
    macro_v1_tick(&s, 2531, 0);
    CHECK(!s.space && s.ctrl);
    macro_v1_tick(&s, 2541, 0);
    CHECK(s.space && s.ctrl);
    macro_v1_input(&s, 0, 2542);
    macro_v1_tick(&s, 2542, 0);
    CHECK(!s.ctrl && !s.space && s.action == V1_IDLE);
    macro_v1_input(&s, V1_MIDDLE, 2600);
    macro_v1_input(&s, 0, 2650);
    CHECK(!s.enabled && !s.mode && !macro_v1_led(&s, 2650));
    macro_v1_input(&s, V1_MIDDLE, 2700);
    macro_v1_tick(&s, 3500, 0);
    macro_v1_input(&s, 0, 3501);
    CHECK(!s.enabled);
    macro_v1_input(&s, V1_MIDDLE, 3600);
    macro_v1_input(&s, 0, 3650);
    macro_v1_input(&s, V1_MIDDLE, 3700);
    macro_v1_input(&s, 0, 4500);
    CHECK(s.enabled && s.mode == 1);
    macro_v1_input(&s, V1_BACK | V1_RIGHT, 4510);
    macro_v1_tick(&s, 4510, 0);
    CHECK(s.action == V1_GHOST);
    macro_v1_tick(&s, 4511, 15);
    CHECK(s.deadline == 4536);
    macro_v1_input(&s, V1_MIDDLE | V1_BACK, 4520);
    macro_v1_input(&s, V1_BACK, 4550);
    CHECK(!s.enabled && !s.ctrl && !s.space && !s.click);
    CHECK(!macro_v1_buttons(&s));
    macro_v1_input(&s, 0, 4560);
    macro_v1_input(&s, V1_BACK, 4570);
    CHECK(macro_v1_buttons(&s) == V1_BACK);
    macro_v1_reset(&s);
    macro_v1_input(&s, V1_RIGHT, 0);
    macro_v1_tick(&s, 0, 0);
    CHECK(macro_v1_buttons(&s) == V1_RIGHT && s.action == V1_IDLE);
    s.enabled = true;
    macro_v1_tick(&s, 1, 0);
    CHECK(macro_v1_buttons(&s) == V1_RIGHT && s.action == V1_IDLE);
    for (unsigned mode = 1; mode <= 2; ++mode) {
        macro_v1_reset(&s);
        s.enabled = true;
        s.mode = mode;
        macro_v1_input(&s, V1_RIGHT, 0);
        macro_v1_tick(&s, 0, 0);
        CHECK(s.action == V1_USP && macro_v1_buttons(&s) == 0);
        macro_v1_tick(&s, 1, 0);
        CHECK(s.click && macro_v1_buttons(&s) == V1_LEFT);
        macro_v1_tick(&s, 39, 0);
        CHECK(!s.click && !s.recoil && macro_v1_buttons(&s) == 0);
        macro_v1_input(&s, 0, 40);
        macro_v1_tick(&s, 40, 0);
        CHECK(s.action == V1_IDLE && !s.click);
        macro_v1_input(&s, V1_FORWARD, 41);
        macro_v1_tick(&s, 41, 0);
        CHECK(s.action == V1_IDLE);
    }
    ESP_LOGI("macro_test", "PASS: %u checks", checks);
    return ESP_OK;
}
