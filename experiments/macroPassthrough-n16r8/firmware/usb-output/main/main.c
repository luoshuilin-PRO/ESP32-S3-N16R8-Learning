// Import global project config
#include "config.h"
#include "vision_control.h"
esp_err_t macro_v1_selftest(void);

void app_main(void)
{
    vTaskDelay(pdMS_TO_TICKS(1000)); // At sleep in case of computer boot
    ESP_LOGI(LOG_TITLE, "Starting -MacroPassthrough- application");
    ESP_ERROR_CHECK(macro_v1_selftest());

    // Initialize SPI
    spi_init_master_pc_sender();

    // Initialize hid multiplexer worker (aggregate keyboard report & macro report)
    // Initialize TinyUSB
    tud_user_initialization();
    vision_uart_init();
    hid_init_multiplexer();
    spi_init_slave_hid_receiver();
    ESP_LOGI(LOG_TITLE, "Macro V2 VISION-FIRST: no reacquire delay; takeover release=5ms; click=50/100ms; right=passthrough; no USP/ghost");
    ESP_LOGI(LOG_TITLE, "usb-output started");

    // Leave main() in background
    while (true) {
        vTaskDelay(portMAX_DELAY);
    }
}
