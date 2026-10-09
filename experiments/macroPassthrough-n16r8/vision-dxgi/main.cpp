#include "detector.h"
#include "controller.h"
#include <windows.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <algorithm>
#include <chrono>
#include <filesystem>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;
using Clock = std::chrono::steady_clock;

struct Roi { int x = 950, y = 599, width = 16, height = 21; };
struct HitGate {
    int misses = 0;
    bool active = false;
    bool update(bool hit) {
        if (hit) { misses = 0; active = true; }
        else if (active && ++misses >= 3) active = false;
        return active;
    }
};
static volatile LONG stop_requested = 0;

static BOOL WINAPI on_console(DWORD code) {
    if (code == CTRL_C_EVENT || code == CTRL_BREAK_EVENT) {
        InterlockedExchange(&stop_requested, 1);
        return TRUE;
    }
    return FALSE;
}

static void require(HRESULT hr, const char* what) {
    if (SUCCEEDED(hr)) return;
    std::ostringstream message;
    message << what << " failed: HRESULT 0x" << std::hex << static_cast<unsigned>(hr);
    throw std::runtime_error(message.str());
}

static double qpc_ms(LONGLONG ticks, LONGLONG frequency) {
    return ticks * 1000.0 / frequency;
}

static double percentile(std::vector<double> values, double p) {
    if (values.empty()) return 0;
    std::sort(values.begin(), values.end());
    return values[static_cast<std::size_t>((values.size() - 1) * p)];
}

static int test_samples(const std::filesystem::path& samples) {
    ComPtr<IWICImagingFactory> factory;
    require(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER,
                             IID_PPV_ARGS(&factory)), "WIC factory");
    int checked = 0, failed = 0;
    for (const wchar_t* category : {L"positive", L"interference", L"negative"}) {
        const auto folder = samples / category;
        if (!std::filesystem::is_directory(folder)) throw std::runtime_error("sample folder missing");
        for (const auto& entry : std::filesystem::directory_iterator(folder)) {
            const auto name = entry.path().filename().wstring();
            if (entry.path().extension() != L".png" || name.rfind(L"20261009_", 0) != 0 ||
                name.find(L"_full") != std::wstring::npos) continue;
            ComPtr<IWICBitmapDecoder> decoder;
            require(factory->CreateDecoderFromFilename(entry.path().c_str(), nullptr, GENERIC_READ,
                                                       WICDecodeMetadataCacheOnLoad, &decoder), "decode PNG");
            ComPtr<IWICBitmapFrameDecode> frame;
            require(decoder->GetFrame(0, &frame), "PNG frame");
            UINT width = 0, height = 0;
            require(frame->GetSize(&width, &height), "PNG size");
            ComPtr<IWICFormatConverter> converter;
            require(factory->CreateFormatConverter(&converter), "WIC converter");
            require(converter->Initialize(frame.Get(), GUID_WICPixelFormat32bppBGRA,
                                          WICBitmapDitherTypeNone, nullptr, 0,
                                          WICBitmapPaletteTypeCustom), "convert BGRA");
            std::vector<std::uint8_t> pixels(static_cast<std::size_t>(width) * height * 4);
            require(converter->CopyPixels(nullptr, width * 4, static_cast<UINT>(pixels.size()),
                                          pixels.data()), "read PNG pixels");
            const MaskStats result = detect_bgra(pixels.data(), width, height, width * 4);
            const bool expected = std::wstring(category) != L"negative";
            ++checked;
            if (result.hit != expected) ++failed;
            std::wcout << category << L" " << name << L" pixels=" << result.count
                       << L" hit=" << result.hit << L" expected=" << expected << L"\n";
        }
    }
    std::cout << "Sample result: " << checked - failed << "/" << checked << " correct\n";
    return checked == 11 && failed == 0 ? 0 : 1;
}

struct CaptureDevice {
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> context;
    ComPtr<IDXGIOutput1> output;
    ComPtr<IDXGIOutputDuplication> duplicate;
    ComPtr<ID3D11Texture2D> staging;
    DXGI_OUTPUT_DESC desc{};
};

static CaptureDevice open_capture(const Roi& roi) {
    ComPtr<IDXGIFactory1> factory;
    require(CreateDXGIFactory1(IID_PPV_ARGS(&factory)), "DXGI factory");
    for (UINT a = 0;; ++a) {
        ComPtr<IDXGIAdapter1> adapter;
        if (factory->EnumAdapters1(a, &adapter) == DXGI_ERROR_NOT_FOUND) break;
        for (UINT o = 0;; ++o) {
            ComPtr<IDXGIOutput> output;
            if (adapter->EnumOutputs(o, &output) == DXGI_ERROR_NOT_FOUND) break;
            DXGI_OUTPUT_DESC desc{};
            require(output->GetDesc(&desc), "output description");
            const RECT r = desc.DesktopCoordinates;
            if (roi.x < r.left || roi.y < r.top || roi.x + roi.width > r.right ||
                roi.y + roi.height > r.bottom) continue;
            if (desc.Rotation != DXGI_MODE_ROTATION_IDENTITY &&
                desc.Rotation != DXGI_MODE_ROTATION_UNSPECIFIED)
                throw std::runtime_error("rotated monitor is not supported by this first version");
            CaptureDevice capture;
            capture.desc = desc;
            require(D3D11CreateDevice(adapter.Get(), D3D_DRIVER_TYPE_UNKNOWN, nullptr,
                                      D3D11_CREATE_DEVICE_BGRA_SUPPORT, nullptr, 0,
                                      D3D11_SDK_VERSION, &capture.device, nullptr,
                                      &capture.context), "D3D11 device");
            require(output.As(&capture.output), "DXGI Output1");
            require(capture.output->DuplicateOutput(capture.device.Get(), &capture.duplicate),
                    "DuplicateOutput");
            D3D11_TEXTURE2D_DESC texture{};
            texture.Width = roi.width;
            texture.Height = roi.height;
            texture.MipLevels = 1;
            texture.ArraySize = 1;
            texture.Format = DXGI_FORMAT_B8G8R8A8_UNORM;
            texture.SampleDesc.Count = 1;
            texture.Usage = D3D11_USAGE_STAGING;
            texture.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
            require(capture.device->CreateTexture2D(&texture, nullptr, &capture.staging),
                    "ROI staging texture");
            return capture;
        }
    }
    throw std::runtime_error("ROI is outside active displays; check monitor and physical coordinates");
}

static int run_live(const Roi& roi, int seconds, bool click, const std::wstring& port,
                    bool custom_roi) {
    const Roi old_roi{911, 595, 84, 25};
    const Roi capture_roi = custom_roi ? roi : old_roi;
    const CaptureDevice capture = open_capture(capture_roi);
    std::unique_ptr<Controller> controller;
    HWND target = nullptr;
    if (click) {
        target = GetForegroundWindow();
        if (!target || target == GetConsoleWindow())
            throw std::runtime_error("switch to the game before click mode starts");
        controller = std::make_unique<Controller>(port, target);
    }
    const RECT display = capture.desc.DesktopCoordinates;
    const D3D11_BOX box{static_cast<UINT>(capture_roi.x - display.left),
                        static_cast<UINT>(capture_roi.y - display.top), 0,
                        static_cast<UINT>(capture_roi.x - display.left + capture_roi.width),
                        static_cast<UINT>(capture_roi.y - display.top + capture_roi.height), 1};
    LARGE_INTEGER frequency{};
    QueryPerformanceFrequency(&frequency);
    std::cout << "DXGI " << (click ? "VC1 CLICK" : "read-only") << " ROI "
              << roi.x << "," << roi.y << " " << roi.width << "x" << roi.height;
    if (!custom_roi) std::cout << " OR " << old_roi.x << "," << old_roi.y << " "
                               << old_roi.width << "x" << old_roi.height;
    std::cout << (click ? "; HIT=continuous click, third missed frame=STOP.\n"
                        : "; no COM or HID output.\n")
              << "Press Ctrl+C to stop.\n";
    auto start = Clock::now();
    auto report = start;
    int frames = 0, hits = 0, recent_frames = 0, recent_hits = 0;
    bool previous_hit = false;
    HitGate gate;
    std::vector<double> present_to_decision;
    std::vector<double> copy_and_detect;
    while (!stop_requested && Clock::now() - start < std::chrono::seconds(seconds)) {
        if (click && (GetAsyncKeyState(VK_F8) & 0x8000)) {
            std::cout << "F8 pressed; clicking stopped.\n";
            break;
        }
        DXGI_OUTDUPL_FRAME_INFO info{};
        ComPtr<IDXGIResource> resource;
        const HRESULT hr = capture.duplicate->AcquireNextFrame(100, &info, &resource);
        if (hr == DXGI_ERROR_WAIT_TIMEOUT) {
            if (controller) controller->check();
            continue;
        }
        require(hr, "AcquireNextFrame");
        try {
            if (info.LastPresentTime.QuadPart) {
                const auto frame_start = Clock::now();
                ComPtr<ID3D11Texture2D> texture;
                require(resource.As(&texture), "frame texture");
                capture.context->CopySubresourceRegion(capture.staging.Get(), 0, 0, 0, 0,
                                                       texture.Get(), 0, &box);
                D3D11_MAPPED_SUBRESOURCE mapped{};
                require(capture.context->Map(capture.staging.Get(), 0, D3D11_MAP_READ, 0,
                                             &mapped), "map ROI texture");
                const auto* pixels = static_cast<const std::uint8_t*>(mapped.pData);
                const int stride = static_cast<int>(mapped.RowPitch);
                const auto* new_pixels = pixels +
                    static_cast<std::size_t>(roi.y - capture_roi.y) * stride +
                    static_cast<std::size_t>(roi.x - capture_roi.x) * 4;
                const MaskStats current = detect_bgra(new_pixels, roi.width, roi.height, stride);
                const MaskStats old = custom_roi ? MaskStats{} :
                    detect_bgra(pixels, old_roi.width, old_roi.height, stride);
                capture.context->Unmap(capture.staging.Get(), 0);
                const bool hit = gate.update(current.hit || old.hit);
                if (controller) {
                    if (GetForegroundWindow() != target) {
                        controller->publish(false);
                        throw std::runtime_error("target window lost focus; clicking stopped");
                    }
                    controller->publish(hit);
                    controller->check();
                }
                LARGE_INTEGER now{};
                QueryPerformanceCounter(&now);
                const double age = qpc_ms(now.QuadPart - info.LastPresentTime.QuadPart,
                                          frequency.QuadPart);
                const double cost = std::chrono::duration<double, std::milli>(
                    Clock::now() - frame_start).count();
                if (age >= 0 && age < 1000) present_to_decision.push_back(age);
                copy_and_detect.push_back(cost);
                ++frames; ++recent_frames;
                if (hit) { ++hits; ++recent_hits; }
                if (hit != previous_hit) {
                    std::cout << (hit ? "HIT " : "CLEAR ")
                              << "new_pixels=" << current.count << " old_pixels=" << old.count
                              << " age_ms="
                              << std::fixed << std::setprecision(2) << age << "\n";
                    previous_hit = hit;
                }
            }
        } catch (...) {
            capture.duplicate->ReleaseFrame();
            throw;
        }
        require(capture.duplicate->ReleaseFrame(), "ReleaseFrame");
        const auto now = Clock::now();
        if (now - report >= std::chrono::seconds(1)) {
            const double span = std::chrono::duration<double>(now - report).count();
            std::cout << "frames/s=" << std::fixed << std::setprecision(1)
                      << recent_frames / span << " hit_frames=" << recent_hits
                      << " present_to_decision_p50=" << percentile(present_to_decision, 0.5)
                      << "ms copy_detect_p50=" << percentile(copy_and_detect, 0.5)
                      << "ms\n";
            recent_frames = recent_hits = 0;
            report = now;
        }
    }
    if (controller) controller->check();
    std::cout << "SUMMARY frames=" << frames << " hit_frames=" << hits
              << " present_to_decision_p50/p95=" << percentile(present_to_decision, 0.5)
              << "/" << percentile(present_to_decision, 0.95) << "ms"
              << " copy_detect_p50/p95=" << percentile(copy_and_detect, 0.5)
              << "/" << percentile(copy_and_detect, 0.95) << "ms\n";
    return frames ? 0 : 2;
}

int wmain(int argc, wchar_t** argv) {
    try {
        SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        SetConsoleCtrlHandler(on_console, TRUE);
        require(CoInitializeEx(nullptr, COINIT_MULTITHREADED), "COM initialization");
        Roi roi;
        int seconds = 30;
        std::filesystem::path samples;
        std::wstring port = L"COM4";
        bool click = false, probe = false, protocol_test = false, custom_roi = false;
        for (int i = 1; i < argc; ++i) {
            const std::wstring arg = argv[i];
            if (arg == L"--roi" && i + 4 < argc) {
                custom_roi = true;
                roi.x = std::stoi(argv[++i]); roi.y = std::stoi(argv[++i]);
                roi.width = std::stoi(argv[++i]); roi.height = std::stoi(argv[++i]);
            } else if (arg == L"--seconds" && i + 1 < argc) {
                seconds = std::stoi(argv[++i]);
            } else if (arg == L"--sample-dir" && i + 1 < argc) {
                samples = argv[++i];
            } else if (arg == L"--port" && i + 1 < argc) {
                port = argv[++i];
            } else if (arg == L"--click") {
                click = true;
            } else if (arg == L"--serial-probe") {
                probe = true;
            } else if (arg == L"--protocol-test") {
                protocol_test = true;
            } else {
                throw std::runtime_error("usage: vision_dxgi [--roi x y w h] [--seconds N] [--sample-dir path] [--serial-probe] [--click] [--port COM4]");
            }
        }
        if (roi.width <= 0 || roi.height <= 0 || seconds <= 0)
            throw std::runtime_error("ROI dimensions and seconds must be positive");
        if ((click ? 1 : 0) + (probe ? 1 : 0) + (protocol_test ? 1 : 0) +
            (!samples.empty() ? 1 : 0) > 1)
            throw std::runtime_error("choose only one of --click, --serial-probe, --protocol-test, --sample-dir");
        int result;
        if (protocol_test) {
            const std::array<std::uint8_t, 16> expected{
                0x56, 0x43, 0x31, 0x21, 0x7b, 0, 0, 0, 1, 0, 0, 0,
                0x28, 0xd3, 0x04, 0xbc};
            HitGate gate;
            const bool gate_ok = !gate.update(false) && gate.update(true) &&
                gate.update(false) && gate.update(false) && !gate.update(false) &&
                !gate.update(false) && gate.update(true);
            result = vc1_packet(123, 1) == expected && gate_ok ? 0 : 1;
            std::cout << "VC1 packet test: " << (result ? "FAIL" : "PASS") << "\n";
        } else if (probe) {
            SerialLink serial(port);
            std::cout << "VC1 HELLO: B native USB "
                      << (serial.native_ready() ? "ready" : "not ready") << "\n";
            result = serial.native_ready() ? 0 : 2;
        } else {
            result = samples.empty() ? run_live(roi, seconds, click, port, custom_roi)
                                     : test_samples(samples);
        }
        CoUninitialize();
        return result;
    } catch (const std::exception& error) {
        std::cerr << "ERROR: " << error.what() << "\n";
        CoUninitialize();
        return 1;
    }
}
