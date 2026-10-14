# HID-Bridge 双板鼠标透传与视觉实验

本目录记录 2026-10-13 至 2026-10-14 的双板实验。固件采用上游 [ESP32-S3-HID-Bridge v0.1.2](https://github.com/guobaren/ESP32-S3-HID-Bridge)；这里归档的是配套 Windows 程序，并非上游固件的修改版。

## 硬件连接

- A/M 板：原生 USB 接真实鼠标，COM 接运行 Python 程序的电脑；A 板 USB-OTG 供电触点已短接。
- B/P 板：原生 USB 接接收鼠标 HID 的电脑。B 板的 COM 可用于供电/烧录，使用时避免多路供电冲突。
- 板间：A GPIO17 TX → B GPIO18 RX，A GPIO18 RX ← B GPIO17 TX，GND ↔ GND。不互接 5V/3.3V，也不沿用旧 SPI 八线。
- 单机或双机均可：双机时 OBS/NDI 将画面传到副机，A 板 COM 接副机，B 板 USB 接主机；单机时相应接口接同一台电脑。

## 目录

- [current/ndi-yolo-viewer](current/ndi-yolo-viewer/README.md)：当前 OBS/NDI + YOLO 工具源码。保留旧版跟随行为、模型检查与延迟统计；串口输出默认关闭。
- [current/hid-bridge-python](current/hid-bridge-python/README.md)：串口身份查询和手动输入测试。
- [current/hid-bridge-diagnostics](current/hid-bridge-diagnostics/README.md)：端口、固件与协议诊断。
- [previous/ndi-yolo-viewer](previous/ndi-yolo-viewer/README.md)：2026-10-13 迁移包内的软件源码快照，用于对照此前行为。
- [previous/source-only.zip](previous/source-only.zip)：上述旧版软件源码的便携 ZIP；不含虚拟环境、模型、样本或第三方安装包。SHA-256：`EE1FE3F03DD6CF46BBD40F8583215D3E683DFA30B7D11EB03E6F9C5E70BD85E6`。

安装时先阅读对应 README。当前视觉程序与串口工具必须保持上述同级目录结构，因为它会引用串口工具的控制器模块。`current/ndi-yolo-viewer/models/cf.onnx` 需由模型持有者自行放入；本仓库不分发该模型。

## 旧离线迁移整包

本机原有 `HID-Bridge-Toolkit-20261013-221046.zip`，约 153 MiB，SHA-256：`4f80ba8aacf49a9622e83e1d85a1b01fdf048b3d4b9a6fd6d8e864328dbf56de`。它包含用户模型、游戏画面样本、Python 安装器和离线依赖，不适合作为公开 Git 源码提交；本仓库只提供不含这些内容的旧版源码包。若需跨电脑完整离线迁移，仍使用本机原整包并遵循其中的第三方许可说明。

## 验证边界

用户已确认双板实体鼠标透传及串口手动测试成功；OBS/NDI 画面和 `cf.onnx` 识别成功。当前程序的输出动作与模型准确率依赖具体接线、游戏画面和参数，归档不代表跨电脑实机验证。串口每次只允许一个程序占用，切换主机窗口前先停止输出。
