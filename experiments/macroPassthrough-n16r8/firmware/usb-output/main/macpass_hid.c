#include "config.h"
#include "macro_v1.h"
#include "status_led.h"
#include "esp_random.h"
#include "vision_control.h"

static QueueHandle_t reports;

static int8_t take_axis(int *pending)
{
    int part = *pending > 127 ? 127 : (*pending < -127 ? -127 : *pending);
    *pending -= part;
    return (int8_t)part;
}

static void merge_keyboard(hid_keyboard_report_t *out,
                           const hid_keyboard_report_t *physical,
                           const macro_v1_t *state)
{
    *out = *physical;
    if (state->ctrl) out->modifier |= KEYBOARD_MODIFIER_LEFTCTRL;
    if (!state->space) return;
    for (unsigned i = 0; i < 6; ++i)
        if (out->keycode[i] == HID_KEY_SPACE) return;
    for (unsigned i = 0; i < 6; ++i) {
        if (!out->keycode[i]) {
            out->keycode[i] = HID_KEY_SPACE;
            return;
        }
    }
}

static void hid_worker(void *arg)
{
    macro_v1_t state;
    vision_click_t vision = {0};
    macro_v1_reset(&state);
    hid_keyboard_report_t physical = {0}, sent_key = {0}, key = {0};
    hid_mouse_report_t mouse = {0};
    uint8_t sent_buttons = 0;
    uint8_t last_raw_buttons = 0;
    bool connected = false, need_neutral = true;
    bool key_pending = false, mouse_pending = false;
    int extra_y = 0;
    status_led_init();
    for (;;) {
        if (!tud_ready()) {
            vision_invalidate();
            vision = (vision_click_t){0};
            macro_v1_reset(&state);
            physical = sent_key = key = (hid_keyboard_report_t){0};
            mouse = (hid_mouse_report_t){0};
            sent_buttons = 0;
            last_raw_buttons = 0;
            extra_y = 0;
            connected = false;
            need_neutral = true;
            key_pending = mouse_pending = false;
            xQueueReset(reports);
            status_led_set(false);
            vTaskDelay(1);
            continue;
        }
        if (!connected) {
            connected = true;
            key_pending = mouse_pending = true;
        }
        // Retain each edge until accepted by USB, before advancing the engine.
        if (key_pending || mouse_pending) {
            // Cancel an automatic press even while USB is stalled.
            int64_t pending_now = esp_timer_get_time() / 1000;
            vision_grant_t pending_grant = vision_get();
            if (vision.running && !vision_fresh(pending_grant, pending_now)) {
                vision_step(&vision, pending_grant, (sent_buttons & V1_LEFT) != 0, pending_now);
                state.left_suspended = false;
                macro_v1_tick(&state, pending_now, esp_random());
                mouse.buttons = vision_buttons(&vision, macro_v1_buttons(&state));
                mouse_pending = true;
            }
            if (tud_hid_ready()) {
                if (key_pending) {
                    if (tud_hid_keyboard_report(HID_ITF_PROTOCOL_KEYBOARD, key.modifier, key.keycode)) {
                        sent_key = key;
                        key_pending = false;
                    }
                } else if (tud_hid_mouse_report(HID_ITF_PROTOCOL_MOUSE, mouse.buttons,
                                               mouse.x, mouse.y, mouse.wheel, mouse.pan)) {
                    sent_buttons = mouse.buttons;
                    vision_sent(&vision, esp_timer_get_time() / 1000);
                    mouse = (hid_mouse_report_t){0};
                    mouse_pending = false;
                }
            }
            vTaskDelay(1);
            continue;
        }
        hid_transmit_t report;
        bool received = xQueueReceive(reports, &report, 1) == pdTRUE;
        int64_t now = esp_timer_get_time() / 1000;
        bool old_enabled = state.enabled;
        uint8_t old_mode = state.mode, old_action = state.action;
        if (received && report.header == HEADER_HID_MOUSE) {
            mouse = report.event.mouse;
            if (last_raw_buttons != mouse.buttons) {
                ESP_LOGI("mouse_input", "raw=0x%02x enabled=%d mode=%u blocked=0x%02x neutral=%d",
                         mouse.buttons, state.enabled, state.mode, state.blocked, need_neutral);
                last_raw_buttons = mouse.buttons;
            }
            // A reconnect never activates a macro from an already-held button.
            if (need_neutral) {
                if (!mouse.buttons) need_neutral = false;
            } else {
                macro_v1_input(&state, mouse.buttons, now);
            }
        } else if (received && report.header == HEADER_HID_KEYBOARD) {
            physical = report.event.keyboard;
        }
        vision_step(&vision, vision_get(), (sent_buttons & V1_LEFT) != 0, now);
        state.left_suspended = vision.running;
        macro_v1_tick(&state, now, esp_random());
        mouse.buttons = vision_buttons(&vision, macro_v1_buttons(&state));
        extra_y += mouse.y + state.recoil;
        mouse.y = take_axis(&extra_y);
        mouse_pending = vision_needs_report(&vision) || mouse.buttons != sent_buttons || mouse.x || mouse.y || mouse.wheel || mouse.pan;
        merge_keyboard(&key, &physical, &state);
        key_pending = memcmp(&key, &sent_key, sizeof(key)) != 0;
        status_led_set(macro_v1_led(&state, now));
        if (old_enabled != state.enabled || old_mode != state.mode || old_action != state.action) {
            ESP_LOGI("macro_v1", "enabled=%d mode=%u action=%u", state.enabled, state.mode, state.action);
        }
    }
}

void hid_init_multiplexer(void)
{
    reports = xQueueCreate(64, sizeof(hid_transmit_t));
    assert(reports);
    BaseType_t ok = xTaskCreatePinnedToCore(hid_worker, "HID V1", 4096, NULL, 22, NULL, 0);
    assert(ok == pdPASS);
}

void hid_add_report(hid_transmit_t report)
{
    xQueueSend(reports, &report, portMAX_DELAY);
}
