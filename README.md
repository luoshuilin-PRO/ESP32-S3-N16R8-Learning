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

2026-10-08：B 板当前为 VISION-FIRST 版，已烧录并通过 87 项板上状态机自检及隔离串口测试。Windows 红名像素工具与当前 B 固件源码已归档；用户反馈触发延迟仍大，尚未获得端到端耗时数据。C 板摄像头方案仍在可行性讨论，未接线或烧录。详情见[双板实验记录](experiments/macroPassthrough-n16r8/README.md)。

## 官方资料

- [乐鑫 ESP32-S3 文档](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/)
- [ESP32-S3 芯片数据手册](https://documentation.espressif.com/esp32_s3_datasheet_en.pdf)

当前双板项目使用 ESP-IDF v5.4-dirty；旧演示宏和 RIGHT-USP 版保存在 Git 历史中，当前 B 固件不执行它们。
