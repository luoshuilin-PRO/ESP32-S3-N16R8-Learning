#include "serial_link.h"
#include <chrono>
#include <stdexcept>
#include <string>

std::array<std::uint8_t, 16> vc1_packet(std::uint32_t seq, std::uint8_t command) {
    std::array<std::uint8_t, 16> p{'V', 'C', '1', '!'};
    for (int i = 0; i < 4; ++i) p[4 + i] = static_cast<std::uint8_t>(seq >> (8 * i));
    p[8] = command;
    std::uint32_t crc = 0xffffffffU;
    for (int i = 0; i < 12; ++i) {
        crc ^= p[i];
        for (int b = 0; b < 8; ++b)
            crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1U)));
    }
    crc = ~crc;
    for (int i = 0; i < 4; ++i) p[12 + i] = static_cast<std::uint8_t>(crc >> (8 * i));
    return p;
}

SerialLink::SerialLink(const std::wstring& port) {
    const std::wstring path = L"\\\\.\\" + port;
    handle_ = CreateFileW(path.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr,
                          OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (handle_ == INVALID_HANDLE_VALUE)
        throw std::runtime_error("cannot open COM port; check port name and other serial monitors");
    try {
        DCB dcb{};
        dcb.DCBlength = sizeof(dcb);
        if (!GetCommState(handle_, &dcb)) throw std::runtime_error("GetCommState failed");
        dcb.BaudRate = 115200;
        dcb.ByteSize = 8;
        dcb.Parity = NOPARITY;
        dcb.StopBits = ONESTOPBIT;
        dcb.fBinary = TRUE;
        dcb.fParity = FALSE;
        dcb.fOutxCtsFlow = FALSE;
        dcb.fOutxDsrFlow = FALSE;
        dcb.fDtrControl = DTR_CONTROL_DISABLE;
        dcb.fRtsControl = RTS_CONTROL_DISABLE;
        dcb.fOutX = FALSE;
        dcb.fInX = FALSE;
        if (!SetCommState(handle_, &dcb)) throw std::runtime_error("SetCommState failed");
        COMMTIMEOUTS timeouts{};
        timeouts.ReadIntervalTimeout = MAXDWORD;
        timeouts.ReadTotalTimeoutConstant = 5;
        timeouts.WriteTotalTimeoutConstant = 80;
        if (!SetCommTimeouts(handle_, &timeouts)) throw std::runtime_error("SetCommTimeouts failed");
        PurgeComm(handle_, PURGE_RXCLEAR | PURGE_TXCLEAR);
        seq_ = static_cast<std::uint32_t>(GetTickCount64() & 0x7fffffffU);
        native_ready_ = exchange(2, 1000);
    } catch (...) {
        CloseHandle(handle_);
        handle_ = INVALID_HANDLE_VALUE;
        throw;
    }
}

SerialLink::~SerialLink() {
    stop_best_effort();
    if (handle_ != INVALID_HANDLE_VALUE) CloseHandle(handle_);
}

void SerialLink::write_packet(std::uint8_t command) {
    const auto p = vc1_packet(++seq_, command);
    DWORD written = 0;
    if (!WriteFile(handle_, p.data(), static_cast<DWORD>(p.size()), &written, nullptr) ||
        written != p.size())
        throw std::runtime_error("COM write failed");
    last_write_done_ = std::chrono::steady_clock::now();
}

bool SerialLink::exchange(std::uint8_t command, int timeout_ms) {
    write_packet(command);
    const std::string wanted = "VC1 ACK " + std::to_string(seq_) + " " +
                               std::to_string(command) + " ";
    const auto deadline = std::chrono::steady_clock::now() +
                          std::chrono::milliseconds(timeout_ms);
    while (std::chrono::steady_clock::now() < deadline) {
        char chunk[128];
        DWORD read = 0;
        if (!ReadFile(handle_, chunk, sizeof(chunk), &read, nullptr))
            throw std::runtime_error("COM read failed");
        buffer_.append(chunk, read);
        std::size_t end;
        while ((end = buffer_.find('\n')) != std::string::npos) {
            const std::string line = buffer_.substr(0, end);
            buffer_.erase(0, end + 1);
            if (line.rfind(wanted, 0) == 0)
                return line.substr(wanted.size()).find('1') == 0;
        }
        if (buffer_.size() > 4096) buffer_.clear();
    }
    throw std::runtime_error("B did not ACK VC1 within timeout; clicking stopped");
}

void SerialLink::stop_best_effort() {
    if (handle_ == INVALID_HANDLE_VALUE) return;
    try { write_packet(0); } catch (...) {}
}
