# ESP32-S3 N16R8 学习仓库

记录 ESP32-S3 学习笔记、硬件、实验与进度。

## 已有硬件

| 编号 | 用户确认的型号 | 排针状态 |
|---|---|---|
| A | ESP32-S3 N16R8 | 已焊接 |
| B | ESP32-S3 N16R8 | 已用于双板接线；最终焊点检查待补录 |
| C（已购买，待实物核对） | ESP32-S3 N16R8 CAM + OV2640 | 尚未接入双板项目 |

两板已实测 ESP32-S3 rev v0.2、16MB Flash、8MB PSRAM；CH343 COM 口用于烧录和日志，原生 USB 用于 HID。用户确认仅 A 板短接 USB-OTG 供电焊盘，B 未改；焊后带载电压与实物版本待补录。

## 学习入口

- [硬件清单](hardware/硬件清单.md)
- [学习进度](学习进度.md)
- [第一步：确认板卡与连接](notes/00-开始学习.md)
- [实验记录模板](experiments/实验记录模板.md)
- [macroPassthrough 双板接线、焊接、编译烧录与源码快照](experiments/macroPassthrough-n16r8/README.md)

2026-10-09：B 板仍为 VISION-FIRST 版，A/B 固件本轮未重刷。已归档 Python 快速版和 DXGI 逐帧版；用户在游戏中验证 DXGI 识别切换及 COM4 ACTIVE/STOP ACK，临时窗口验证 B HID 持续点击。当前 DXGI 源码为双 ROI；后续只保留新版小 ROI 是待实施意向。首击端到端延迟仍未测，项目按用户要求暂时停止。详情见[双板实验记录](experiments/macroPassthrough-n16r8/README.md)。

## 官方资料

- [乐鑫 ESP32-S3 文档](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/)
- [ESP32-S3 芯片数据手册](https://documentation.espressif.com/esp32_s3_datasheet_en.pdf)

当前双板项目使用 ESP-IDF v5.4-dirty；旧演示宏和 RIGHT-USP 版保存在 Git 历史中，当前 B 固件不执行它们。
