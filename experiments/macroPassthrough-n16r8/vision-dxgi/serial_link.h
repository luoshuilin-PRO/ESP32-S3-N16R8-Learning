#pragma once
#include <windows.h>
#include <array>
#include <chrono>
#include <cstdint>
#include <string>

std::array<std::uint8_t, 16> vc1_packet(std::uint32_t seq, std::uint8_t command);

class SerialLink {
public:
    explicit SerialLink(const std::wstring& port);
    ~SerialLink();
    SerialLink(const SerialLink&) = delete;
    SerialLink& operator=(const SerialLink&) = delete;

    bool exchange(std::uint8_t command, int timeout_ms = 120);
    void stop_best_effort();
    bool native_ready() const { return native_ready_; }
    std::chrono::steady_clock::time_point last_write_done() const { return last_write_done_; }

private:
    HANDLE handle_ = INVALID_HANDLE_VALUE;
    std::uint32_t seq_ = 0;
    bool native_ready_ = false;
    std::chrono::steady_clock::time_point last_write_done_{};
    std::string buffer_;
    void write_packet(std::uint8_t command);
};
