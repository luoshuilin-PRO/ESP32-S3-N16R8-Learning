#include "vision_control.h"
#include "driver/uart.h"
#include "esp_timer.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "tusb.h"
#include <string.h>
#include <stdio.h>
#include <assert.h>
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;
static vision_grant_t grant;
vision_grant_t vision_get(void)
{
    portENTER_CRITICAL(&lock);
    vision_grant_t value = grant;
    portEXIT_CRITICAL(&lock);
    return value;
}
void vision_invalidate(void)
{
    portENTER_CRITICAL(&lock);
    grant.active = false;
    portEXIT_CRITICAL(&lock);
}
static uint32_t le32(const uint8_t *p)
{
    return p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static void uart_worker(void *unused)
{
    uint8_t buf[16];
    unsigned used = 0;
    bool session = false;
    uint32_t seq = 0;
    int64_t last_packet = 0;
    for (;;) {
        uint8_t b;
        int64_t now = esp_timer_get_time() / 1000;
        if (now - last_packet > VISION_LEASE_MS) {
            vision_invalidate();
            session = false;
        }
        if (uart_read_bytes(UART_NUM_0, &b, 1, pdMS_TO_TICKS(5)) != 1) continue;
        buf[used++] = b;
        if (used < 4) continue;
        if (memcmp(buf, "VC1!", 4) != 0) {
            memmove(buf, buf + 1, --used);
            continue;
        }
        if (used != 16) continue;
        used = 0;
        if (le32(buf + 12) != vision_crc(buf, 12) || buf[9] || buf[10] || buf[11]) continue;
        uint32_t incoming = le32(buf + 4);
        uint8_t command = buf[8];
        now = esp_timer_get_time() / 1000;
        if (command == 2) {
            session = true;
            seq = incoming;
            vision_invalidate();
        } else if (command == 0) {
            vision_invalidate();
            if (!session || (int32_t)(incoming - seq) <= 0) continue;
            seq = incoming;
        } else if (command == 1 && session && (int32_t)(incoming - seq) > 0) {
            seq = incoming;
            portENTER_CRITICAL(&lock);
            grant = (vision_grant_t){seq, now, tud_ready()};
            portEXIT_CRITICAL(&lock);
        } else continue;
        last_packet = now;
        char ack[80];
        int n = snprintf(ack, sizeof(ack), "\nVC1 ACK %lu %u %u\n", (unsigned long)seq, command, tud_ready());
        uart_write_bytes(UART_NUM_0, ack, n);
    }
}
void vision_uart_init(void)
{
    uart_config_t config = {
        .baud_rate = 115200, .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE, .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE, .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &config));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0, 43, 44, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 512, 0, 0, NULL, 0));
    assert(xTaskCreate(uart_worker, "vision_uart", 3072, NULL, 10, NULL) == pdPASS);
    ESP_LOGI("vision", "VC1 UART0 115200 ready; lease=180ms; click=50/100ms; vision-left priority");
}
