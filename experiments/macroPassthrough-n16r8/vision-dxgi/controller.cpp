#include "controller.h"
#include <iostream>
#include <stdexcept>

using Clock = std::chrono::steady_clock;

Controller::Controller(const std::wstring& port, HWND target) : serial_(port), target_(target) {
    if (!serial_.native_ready())
        throw std::runtime_error("B native USB is not ready; connect B native USB before clicking");
    worker_ = std::thread(&Controller::run, this);
    std::cout << "VC1 ready. ACTIVE is sent only after fresh red pixels are detected.\n";
}

Controller::~Controller() {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        closing_ = true;
    }
    changed_.notify_all();
    if (worker_.joinable()) worker_.join();
    serial_.stop_best_effort();
}

void Controller::publish(bool hit) {
    bool transition;
    {
        std::lock_guard<std::mutex> lock(mutex_);
        transition = hit_ != hit;
        hit_ = hit;
        last_frame_ = Clock::now();
        if (transition) transition_time_ = last_frame_;
    }
    if (transition) changed_.notify_one();
}

void Controller::check() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!error_.empty()) throw std::runtime_error(error_);
}

void Controller::run() {
    bool sent_hit = false;
    auto last_control = Clock::now();
    try {
        for (;;) {
            bool desired = false;
            Clock::time_point transition_time;
            {
                std::unique_lock<std::mutex> lock(mutex_);
                changed_.wait_for(lock, std::chrono::milliseconds(10), [&] {
                    const bool fresh = hit_ && last_frame_ != Clock::time_point{} &&
                                       Clock::now() - last_frame_ < std::chrono::milliseconds(80);
                    return closing_ || fresh != sent_hit;
                });
                if (closing_) break;
                desired = hit_ && last_frame_ != Clock::time_point{} &&
                          Clock::now() - last_frame_ < std::chrono::milliseconds(80);
                transition_time = hit_ && !desired
                    ? last_frame_ + std::chrono::milliseconds(80) : transition_time_;
            }
            const auto now = Clock::now();
            const bool focus_lost = GetForegroundWindow() != target_;
            const bool f8_pressed = (GetAsyncKeyState(VK_F8) & 0x8000) != 0;
            if (focus_lost || f8_pressed) desired = false;
            if (desired != sent_hit || now - last_control >= std::chrono::milliseconds(40)) {
                const bool transition = desired != sent_hit;
                const auto command_start = Clock::now();
                if (!serial_.exchange(desired ? 1 : 0))
                    throw std::runtime_error("B native USB disconnected; clicking stopped");
                if (transition) {
                    const double to_write = std::chrono::duration<double, std::milli>(
                        serial_.last_write_done() - transition_time).count();
                    const double round_trip = std::chrono::duration<double, std::milli>(
                        Clock::now() - command_start).count();
                    std::cout << "VC1 " << (desired ? "ACTIVE" : "STOP")
                              << " ACK decision_to_write_ms=" << to_write
                              << " round_trip_ms=" << round_trip << "\n";
                }
                sent_hit = desired;
                last_control = Clock::now();
            }
            if (focus_lost)
                throw std::runtime_error("target window lost focus; clicking stopped");
            if (f8_pressed)
                throw std::runtime_error("F8 pressed; clicking stopped");
        }
    } catch (const std::exception& e) {
        std::lock_guard<std::mutex> lock(mutex_);
        error_ = e.what();
    }
    serial_.stop_best_effort();
}
