# DXGI 逐帧红名检测：第一版

归档说明（2026-10-09）：此目录只保存源码与脚本，不含本机 `build/` 可执行文件、游戏截图样本和串口日志。以下“本机已编译/已验证”描述归档时的开发电脑状态；在新电脑运行前需重新构建。用户已决定暂时停止项目，并提出后续只保留新版小 ROI；此源码仍是双 ROI，尚未实施该意向。

这是一份 Windows 原生 C++ 逐帧检测程序。它等待系统提供新的桌面帧，用 GPU 将指定小区域复制到可读缓冲区，按已有 HSV 规则判断红名。`run.cmd` 是只读诊断；`run-click.cmd` 才会使用现有 VC1 固件经 COM4 控制 B 板。没有修改或重刷 A/B 固件。原来的 `vision-controller` 和 `vision-controller-fast` 均未被替换。

## 运行

本机已编译，可双击 `run.cmd`。默认同时检查旧版 `(911,595)` 的 `84×25` 区域和新版 `(950,599)` 的 `16×21` 区域；任意一个命中即为 `HIT`。两个区域共用一次 DXGI 画面复制。运行 30 秒后输出汇总；按 Ctrl+C 可提前停止。

确认只读检测在游戏里能准确出现 `HIT/CLEAR` 后，再双击 `run-click.cmd`。它会先显示确认提示，三秒后进入 30 秒测试。B 板 COM4 接电脑用于 VC1 指令，B 原生 USB 接电脑用于 HID；A/B 原来的鼠标、独立供电、8 根 SPI 加 GND 接线保持不变。关闭其他占用 COM4 的软件。程序启动先向 B 发 HELLO，只有 B 原生 USB 已就绪才允许进入点击模式；关闭时发 STOP。

点击模式下，第一次 `HIT` 发 ACTIVE，红名持续时约每 40ms 续期一次；连续两帧未命中仍维持连点，第 3 帧未命中才 `CLEAR` 并发 STOP。空闲时定期发送 STOP。连续 80ms 没有新画面帧时撤销视觉许可；目标窗口失焦、按下 F8 或串口失联则发 STOP 并结束测试。B 还有 180ms 许可超时保护。B 板仍按现有 50ms 按下、100ms 松开循环。**不要同时运行旧 Python 检测工具**，它会抢占 COM4。

手动指定坐标和时间：

```powershell
.\build\Release\vision_dxgi.exe --roi 950 599 16 21 --seconds 30
.\build\Release\vision_dxgi.exe --serial-probe --port COM4
.\build\Release\vision_dxgi.exe --click --port COM4 --seconds 30
```

若原生程序文件需要重建，在此目录运行 `build.ps1`。依赖 Visual Studio 2022 C++ Build Tools 和 Windows SDK。离线核对 2026-10-09 新 PNG：

```powershell
.\build\Release\vision_dxgi.exe --sample-dir ..\material-capture\samples
```

## 显示含义

- `HIT`/`CLEAR`：任一区域命中立即 `HIT`，连续第 3 帧两个区域均未命中才 `CLEAR`。`new_pixels` 和 `old_pixels` 是当前帧两个区域的红色像素数。
- `frames/s`：过去约一秒收到的桌面内容更新帧数；与游戏内部 FPS 或实际鼠标点击频率不同。
- `copy_detect`：取小区域 GPU 像素并完成判断的时间。
- `present_to_decision`：DXGI 报告的桌面帧呈现时间到判断完成的时间。它**不包含等待下一帧**，也不包含串口、B 板 USB HID 和游戏响应。
- `p50/p95`：本次运行中的中位数及第 95 百分位。没有新帧时程序等待，不会重复判断旧帧。
- `VC1 ACTIVE/STOP ACK`：B 板确认的状态变化；`decision_to_write_ms` 是识别结果到交给 Windows 串口驱动的耗时，`round_trip_ms` 是写入到收到 B 确认的耗时。两者仍不包含 B 原生 USB 报告被电脑或游戏处理的时间。

两套现存配置的 HSV 数值相同：OpenCV 标度 H=3..12、S>=150、V>=140；至少 10 红色像素、面积占比<=65%、分布宽>=5 高>=3。主要区别是区域位置和大小。`--roi x y w h` 可覆盖为单区域诊断，不再同时检查旧区域。旧区域较大，可能增加红色干扰误报，需在游戏中复核。新增的 11 张截图里，8 张含红名样本命中、3 张无红名样本未命中；4 张“红色干扰”样本仍有红名，不能代表只有干扰的误报测试。

## 2026-10-09 本机验证

- MSVC Release 构建通过；离线新样本 11/11 与标签相符。
- 正常桌面运行 6 秒收到 419 帧，0 命中；`present_to_decision` p50/p95 约 0.7/1.7ms。桌面更新频率随屏幕内容变化，不是固定 FPS。
- 临时在 ROI 放置原始红名裁剪图，程序报告 `HIT red_pixels=110`；图像移走后报告 `CLEAR red_pixels=0`。这一测试约 0.4ms p50，只验证了可见桌面上的新帧检测。
- 先用 COM4 HELLO/STOP 探测确认 B 原生 USB 已就绪；协议数据包与既有 Python VC1 实现逐字节一致，11 张新样本分类与标签一致。
- 随后在临时全屏测试窗口进行真实 B 板 HID 验证：第一次显示红名时收到 11 次左键，红名消失期间保持 11 次；第二次显示红名后累计 21 次，第二次消失后保持 21 次。两次 ACTIVE 与 STOP 都收到 COM4 ACK；识别决定到串口写入约 0.1ms，ACK 往返约 4.6ms。测试窗口的画面更新约 50 帧/秒，鼠标点击只落在该测试窗口，未验证游戏内响应。

用户已在实际游戏中运行只读版和 COM4 点击版：新画面约 200-240 帧/秒，多次 `HIT → ACTIVE ACK → CLEAR → STOP ACK`，ACK 往返约 4.5ms。此日志证明指令到达 B 板，不单独证明每次点击都被游戏接收。双区域与三帧停止规则更新后，在临时窗口分别实测旧区域单独命中（`new_pixels=0 old_pixels=110`）和新区域命中，均出现持续点击、隐藏后停止、再次显示后重启；还需在游戏中复核旧区域可能带来的误报。若程序报告 `DuplicateOutput` 或 `AcquireNextFrame` 错误，可用窗口化或无边框显示；分辨率/显示器模式改变后需重启。实际首击延迟不能把上述亚毫秒数字当作端到端延迟。
