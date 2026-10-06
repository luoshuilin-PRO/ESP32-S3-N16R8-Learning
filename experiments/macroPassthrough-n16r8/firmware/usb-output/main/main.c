// Import global project config
#include "config.h"
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
    hid_init_multiplexer();
    spi_init_slave_hid_receiver();
    ESP_LOGI(LOG_TITLE, "Macro V1 RIGHT-USP: default OFF; middle short=toggle, hold 800ms=mode; right=USP, back=ghost");
    ESP_LOGI(LOG_TITLE, "usb-output started");

    // Leave main() in background
    while (true) {
        vTaskDelay(portMAX_DELAY);
    }
}
