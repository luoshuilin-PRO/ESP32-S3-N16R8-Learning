#include "status_led.h"
#include "driver/rmt_tx.h"
#include "esp_log.h"

static rmt_channel_handle_t channel;
static rmt_encoder_handle_t encoder;
static int previous = -1;

void status_led_set(bool on)
{
    if (!channel || previous == (int)on) return;
    rmt_symbol_word_t symbols[25] = {0};
    uint32_t grb = on ? 0x080000 : 0;
    for (unsigned i = 0; i < 24; ++i) {
        bool bit = (grb & (1UL << (23 - i))) != 0;
        symbols[i].level0 = 1;
        symbols[i].duration0 = bit ? 8 : 4;
        symbols[i].level1 = 0;
        symbols[i].duration1 = bit ? 4 : 8;
    }
    symbols[24].duration0 = 1500;
    symbols[24].duration1 = 1500;
    rmt_transmit_config_t tx = {0};
    ESP_ERROR_CHECK(rmt_transmit(channel, encoder, symbols, sizeof(symbols), &tx));
    ESP_ERROR_CHECK(rmt_tx_wait_all_done(channel, 100));
    previous = on;
}

void status_led_init(void)
{
    rmt_tx_channel_config_t cfg = {
        .gpio_num = 48,
        .clk_src = RMT_CLK_SRC_DEFAULT,
        .resolution_hz = 10000000,
        .mem_block_symbols = 64,
        .trans_queue_depth = 1,
    };
    ESP_ERROR_CHECK(rmt_new_tx_channel(&cfg, &channel));
    rmt_copy_encoder_config_t enc = {};
    ESP_ERROR_CHECK(rmt_new_copy_encoder(&enc, &encoder));
    ESP_ERROR_CHECK(rmt_enable(channel));
    status_led_set(false);
    ESP_LOGI("status_led", "WS2812 GPIO48 ready; board RGB jumper must be connected");
}
