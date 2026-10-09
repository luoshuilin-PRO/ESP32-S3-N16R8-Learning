#include "detector.h"
#include <algorithm>
#include <limits>

MaskStats detect_bgra(const std::uint8_t* pixels, int width, int height, int stride) {
    MaskStats result;
    if (!pixels || width <= 0 || height <= 0 || stride < width * 4) return result;

    int min_x = width, min_y = height, max_x = -1, max_y = -1;
    for (int y = 0; y < height; ++y) {
        const std::uint8_t* row = pixels + static_cast<std::size_t>(y) * stride;
        for (int x = 0; x < width; ++x) {
            const double b = row[x * 4 + 0];
            const double g = row[x * 4 + 1];
            const double r = row[x * 4 + 2];
            const double top = std::max({r, g, b});
            const double bottom = std::min({r, g, b});
            const double delta = top - bottom;
            const double saturation = top > 0 ? delta / top * 255.0 : 0;
            double hue = 0;
            if (delta > 0) {
                if (top == r) {
                    hue = (g - b) / delta;
                    if (hue < 0) hue += 6;
                } else if (top == g) {
                    hue = (b - r) / delta + 2;
                } else {
                    hue = (r - g) / delta + 4;
                }
                hue *= 30.0;
            }
            if (hue < 3.0 || hue > 12.0 || saturation < 150.0 || top < 140.0) continue;
            ++result.count;
            min_x = std::min(min_x, x); max_x = std::max(max_x, x);
            min_y = std::min(min_y, y); max_y = std::max(max_y, y);
        }
    }
    if (result.count) {
        result.width = max_x - min_x + 1;
        result.height = max_y - min_y + 1;
    }
    result.fraction = static_cast<double>(result.count) / (width * height);
    result.hit = result.count >= 10 && result.fraction <= 0.65 &&
                 result.width >= 5 && result.height >= 3;
    return result;
}
