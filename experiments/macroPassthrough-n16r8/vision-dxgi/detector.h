#pragma once
#include <cstdint>

struct MaskStats {
    int count = 0;
    int width = 0;
    int height = 0;
    double fraction = 0;
    bool hit = false;
};

MaskStats detect_bgra(const std::uint8_t* pixels, int width, int height, int stride);
