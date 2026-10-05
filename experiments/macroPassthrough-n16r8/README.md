# ESP32-S3 N16R8 双板 USB HID 透传记录

记录日期：2026-10-06；编译和初次烧录：2026-10-05。
学习状态：学习中。代码验证：两工程编译通过、双板烧录与启动实机验证通过；鼠标部分透传由用户反馈确认，完整功能测试未完成。

## 当前结论

- A 板运行 usb-input，作为 USB Host 接鼠标；B 板运行 usb-output，作为 USB Device 接电脑。
- 使用 ESP-IDF v5.4-dirty 完成适配，未依赖尚未安装完整的 v5.5.4。
- 两板启动日志均确认 16MB Flash、8MB Octal PSRAM，PSRAM 自检通过。
- 用户最新反馈：鼠标左键正常，右键输出类似 `acdefghijklmnopqrstuvwxyz` 的文本。
- 右键输出字母对应原项目自带的 A-Z 演示宏，另有右键鼠标移动宏；不是已证实的硬件故障。
- 用户决定以后再测试宏。本次归档保留默认宏，没有应用此前准备但未获执行的关闭宏修改。
- USB-OTG 焊接方案已讨论；用户未明确确认最终焊点与焊后电压，因此不把焊接验收写为已完成。

## 板卡身份与接口

两块实测均为 ESP32-S3 QFN56 rev v0.2，40MHz 晶振、16MB Flash、8MB 内置 PSRAM。

| 板卡 | 工程 | 最后确认的烧录串口 | 功能 |
|---|---|---|---|
| A | usb-input | COM3，CH343 | 读取鼠标/键盘，经 SPI 发给 B |
| B | usb-output | COM4，CH343 | 接收 SPI，向电脑输出 USB HID |

COM 编号可能随电脑和插口变化。烧录前可用 `python -m esptool --chip esp32s3 --port COM3 read_mac` 核对身份。完整 MAC 保存在本地原工程的 BOARD_A_INFO.txt / BOARD_B_INFO.txt，公开记录不包含设备唯一标识。

- COM 接口：USB 转串口，供电、烧录、串口日志。
- USB 接口：芯片原生 USB，A 接鼠标，B 接电脑。
- 按接口丝印识别；照片正反面左右会反转，不只凭左右位置判断。
- B 的原生 USB 是数据接口，但当前固件没有提供串口调试通道；读取 B 日志、常规烧录仍使用 B 的 COM 接口。

## 板间接线

断开所有电源后接线。两组 SPI 均同号直连，MOSI/MISO 不交叉。

| 信号 | A GPIO | B GPIO | 方向 |
|---|---|---|---|
| 第一组 MOSI | 39 | 39 | A 主机 -> B 从机，HID 数据 |
| 第一组 MISO | 40 | 40 | 第一组总线 |
| 第一组 SCLK | 41 | 41 | A -> B |
| 第一组 CS | 42 | 42 | A -> B |
| 第二组 MOSI | 10 | 10 | B 主机 -> A 从机，键盘 LED 等输出报告 |
| 第二组 MISO | 11 | 11 | 第二组总线 |
| 第二组 SCLK | 12 | 12 | B -> A |
| 第二组 CS | 13 | 13 | B -> A |
| 公共地 | GND | GND | 一根地线作为基本连接 |

共 8 根信号线加 1 根 GND。同板各 GND 属公共地，不必每个 GND 都跨板连接。导线尽量短；当前代码沿用原项目 80MHz SPI 时钟，杜邦线信号完整性和长期稳定性尚未专项验证。

最终使用独立 USB 供电：板间不接 5V，也不接 3.3V。

```text
电脑 COM 数据线 -> A 板 COM 口（供电、日志）
鼠标 -> OTG 转接头 -> A 板 USB 口（需确认 VBUS 输出供电）
A 板 <-> 8 根 SPI 信号线 + GND <-> B 板
B 板 USB 口 -> 电脑（HID 数据）
B 板 COM 口 -> 电脑（仅需烧录/日志时连接）
```

## USB 供电排查与焊接说明

### 观察到的现象

- 单板用 COM 或 USB 供电，用户测得 5V 排针约 4.4-4.5V、3.3V 排针约 3.3V。
- 曾尝试 B 5V 排针向 A 供电，测得电压下降；这不是已验证的供电方案，已停止使用。
- A 板 COM 供电时，用户报告 OTG 输出触点对板上 GND 仅几毫伏、鼠标不亮。触点必须确认为 VBUS，不能把 D+/D- 的电压当供电电压。
- 鼠标加 OTG 接电脑可正常工作。
- A 板可以打印启动日志，但当时没有 HID CONNECTED 事件。板子有电不代表鼠标端有电。

### 找到的参考电路

参考照片标有 `YD-ESP32-23 / 2022-V1.3 / V1120`，与商家图布局高度相似；厂家公开原理图为 V1.4。实物型号/版本及连通关系仍须核对，不能仅凭外观认定全部电路相同。

V1.4 原理图显示：

```text
COM VBUS -------- D1 ---> 板内 5V
原生 USB VBUS --- D2 ---> 板内 5V
5V 排针 --------- D3 ---> 板内 5V
```

二极管允许接口向板内供电，并阻止板内电源反向流向接口。USB-OTG 旁路跨接 D2；IN-OUT 旁路跨接 D3，两者用途不同。这能解释 COM 供电时原生 USB VBUS 没有输出的现象；它是依据参考电路作出的判断，尚无实物电路验收记录。

### A 板 USB-OTG 旁路流程

1. 拔掉所有 USB、鼠标及板间连线，完全断电。
2. 找到背面 `USB-OTG` 旁边的两片焊盘；不是 GND/5V 排针，也不是 IN-OUT 或 USB-JTAG。
3. 根据原理图和通断测量，确认两片分别通向原生 USB VBUS 与板内 5V 电源轨。外侧 5V 排针还可能隔着 D3，不能替代板内电源轨判断。
4. 仅在确认对应后涂少量助焊剂，用少量焊锡桥接两片焊盘。可从有铅约 330°C、无铅约 350°C 起调；快速成桥，避免长时间加热或邻近连锡。
5. 冷却后检查桥接近 0Ω、对 GND 无持续低阻短路，无锡珠。电容充电可能导致短暂蜂鸣。
6. 先不接鼠标及 B 板，仅从 A COM 供电，检查 OTG VBUS 输出电压与发热，再进行带鼠标验证。

只处理 A 的 Host 供电旁路，B 不需要此修改。旁路后 A 原生 USB 固定用作鼠标端口；A COM 供电时，不把 A 原生 USB 再接电脑或其他有源供电端，避免回灌。不要将 5V 接到 GPIO，也不要用 3.3V 代替鼠标 USB 5V。

## 固件快照与改动

`firmware/` 保存本地原工程当前源码快照，而不是未执行的 staging 修改。

- 上游：<https://github.com/arfevrier/macroPassthrough>
- 基线：`90d31a0f3c8b3a9587005d1f4a5bb67c319f57e2`
- 原本地分支：`n16r8-adapt`。
- 保留上游 LICENSE 和 README；上游 README 的行为说明不等于本次全部实测。
- 不归档 build、managed_components、机器绝对路径、完整设备 MAC 或下载凭证。

适配项：

1. 两份 macpass_spi.h 的第二组 GPIO 改为 10/11/12/13，第一组保持 39/40/41/42。
2. 两份 sdkconfig.defaults 指定 ESP32-S3、16MB Flash、Octal PSRAM 自动识别、40MHz PSRAM。
3. IDF 5.4 没有 spi_slave_disable/enable，异常帧恢复改用 spi_slave_free、等待 500ms、重新初始化从机。保持缓冲区和接收任务，未删除恢复功能；异常恢复压力测试未做。
4. 修复 usb-output/main/macpass_tool.h 中 ESP_LOGI 多余参数错误，添加 USB ready 的格式占位符。
5. 两板 main.c 添加各自 started 日志。
6. 依赖锁文件对应 IDF 5.4.0；组件版本保持锁定。

注意：started 日志在创建后台 USB 任务后打印，不能独立证明 USB Host 初始化和设备枚举已完成。

## 编译与烧录复现

先激活 ESP-IDF 5.4 环境并检查 `idf.py --version`。本机实际版本为 `ESP-IDF v5.4-dirty`，不是干净的官方版本；此次编译通过不代表所有 5.4 环境均已测试。

在 firmware/usb-input 中依次执行：

```powershell
idf.py fullclean
idf.py set-target esp32s3
idf.py build
idf.py -p COM3 flash
```

在 firmware/usb-output 中依次执行：

```powershell
idf.py fullclean
idf.py set-target esp32s3
idf.py build
idf.py -p COM4 flash
```

先核对串口身份再烧录，不使用上例端口号盲刷。首次构建会下载受锁文件约束的组件。原工程已执行上述流程；归档副本的源文件一致性已核对，未重新烧录。

## 验证证据与限制

| 项目 | 状态/证据 |
|---|---|
| 输入固件编译 | 通过，应用大小 0x43090 |
| 输出固件编译 | 通过，应用大小 0x3fa40 |
| 两板烧录 | 通过，bootloader/分区表/应用均显示 Hash of data verified |
| Flash 配置 | 两板日志 SPI Flash Size : 16MB |
| PSRAM | 两板 Found 8MB PSRAM device；SPI SRAM memory test OK |
| A 启动 | usb-input started |
| B 启动 | TinyUSB Driver installed；usb-output started |
| B 电脑枚举 | 用户反馈电脑出现新的鼠标设备 |
| 鼠标左键 | 用户反馈正常；未做自动化测试 |
| 鼠标右键 | 用户反馈输出字母；与源码默认右键宏匹配 |
| USB-OTG 焊接验收 | 未记录实物最终焊点、焊后 VBUS 与带载电压 |
| 滚轮、移动、长按、复合 HID、键盘 LED 回传 | 未完整测试 |
| 高速 SPI、掉电恢复与长期稳定性 | 未验证 |

## 宏保留说明

输出工程 config.h 默认宏表包含右键触发 A-Z 和移动鼠标的演示序列，还包括键盘触发宏。macpass_macro.c 有 A/D 同时按下时修改键盘报告的示例。因此当前固件不是严格无修改透传。

后续先在空白文本编辑器中测试，避免宏在终端或重要应用中输入。用户本次明确要求延后宏测试；不调整触发键、不启用未烧录的关闭宏开关。

## 参考资料

- [厂家仓库](https://github.com/vcc-gnd/YD-ESP32-S3)
- [厂家板卡图片](https://github.com/vcc-gnd/YD-ESP32-S3/blob/main/5-public-YD-ESP32-S3-Hardware%20info/YD-ESP32-S3.PNG)
- [厂家 V1.4 原理图](https://github.com/vcc-gnd/YD-ESP32-S3/blob/main/5-public-YD-ESP32-S3-Hardware%20info/YD-ESP32-S3-SCH-V1.4.pdf)
- [乐鑫 USB Host 文档](https://docs.espressif.com/projects/esp-usb/en/latest/esp32s3/usb_host.html)

## 后续待办

- 补录实际板卡版本、A 板 USB-OTG 焊后照片和鼠标端带载电压。
- 记录鼠标型号、移动/滚轮/左右键/断开重连的逐项结果。
- 按用户后续决定测试或关闭演示宏，再对 B 板编译烧录。
- 验证 SPI 可靠性、异常帧恢复及键盘 LED 回传。
