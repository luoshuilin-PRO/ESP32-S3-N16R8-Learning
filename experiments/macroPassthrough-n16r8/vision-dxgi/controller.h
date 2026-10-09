#pragma once
#include "serial_link.h"
#include <chrono>
#include <condition_variable>
#include <mutex>
#include <string>
#include <thread>

class Controller {
public:
    Controller(const std::wstring& port, HWND target);
    ~Controller();
    Controller(const Controller&) = delete;
    Controller& operator=(const Controller&) = delete;

    void publish(bool hit);
    void check();

private:
    void run();
    SerialLink serial_;
    HWND target_ = nullptr;
    std::mutex mutex_;
    std::condition_variable changed_;
    std::thread worker_;
    bool closing_ = false;
    bool hit_ = false;
    std::chrono::steady_clock::time_point last_frame_{};
    std::chrono::steady_clock::time_point transition_time_{};
    std::string error_;
};
