idf_component_register(SRCS "main.c" "macpass_hid.c" "macpass_spi.c" "macpass_usb.c" "macro_v1.c" "macro_v1_test.c" "status_led.c"
                       PRIV_REQUIRES esp_driver_gpio esp_timer esp_driver_rmt esp_hw_support
                       INCLUDE_DIRS ".")
