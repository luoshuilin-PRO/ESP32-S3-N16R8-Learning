# 源码审计：炼狱 / M4 宏及 HID 报告协调

审计日期：2026-10-19。仅静态审计，未编译、未刷机。此分支不影响 main。

## 已实际读取的旧固件源码

- `experiments/macroPassthrough-n16r8/firmware/usb-output/main/macro_v1.c`
- `experiments/macroPassthrough-n16r8/firmware/usb-output/main/macro_v1.h`
- `experiments/macroPassthrough-n16r8/firmware/usb-output/main/macpass_hid.c`
- `experiments/macroPassthrough-n16r8/firmware/usb-output/main/macpass_usb.c`
- `experiments/macroPassthrough-n16r8/firmware/usb-output/main/macro_v2_test.c`
- `experiments/macroPassthrough-n16r8/firmware/usb-output/main/vision_control.c`
- `experiments/macroPassthrough-n16r8/firmware/usb-output/main/CMakeLists.txt`

## 实际状态机调用链

1. `hid_worker` 从 `reports` 队列获取实体 HID 报告。
2. 收到鼠标报告后调用 `macro_v1_input(&state, mouse.buttons, now)` 更新实体按钮状态。
3. `macro_v1_tick(&state, now, esp_random())` 计算动作状态与下一截止时间。
4. `macro_v1_buttons(&state)` 生成合并后的按钮掩码，**宏开启且处于炼狱/M4 时屏蔽物理左键**，再按 `state.click` 加回模拟左键。
5. `vision_buttons` 在视觉接管时覆盖左键位，其他按钮位保留。
6. `tud_hid_mouse_report` 成功提交后更新 `sent_buttons`；待发送期间不推进下一轮报告，避免丢边沿。

## 行为细节与边界

- `macro_v1_tick` 在动作切换时先取消并返回，制造中性过渡；下一 tick 才启动首个按下。
- 炼狱按下时长 `140 + random % 16`，松开 `20 + random % 11`，即 140–155ms / 20–30ms。
- M4 按下 50ms，松开 100ms；松开瞬间设置 `recoil=3`，由 `macpass_hid.c` 累计到鼠标相对 Y 轴。
- `change_mode` 把当前按住的实体左键放入 `blocked`；直到物理松开才允许新动作启动。
- `need_neutral` 在 USB 重连后要求收到全按钮松开的报告才允许重新激活宏。
- `!tud_ready()` 时重置状态、输出缓存、队列及 LED。
- 视觉接管时 `left_suspended=true`，暂停手动宏；本阶段不移植视觉功能，但未来必须保留优先级接口。
- 旧 `macro_v1_buttons` 在启用宏时屏蔽 BACK/FORWARD 侧键；这是旧固件现有行为，不应未经确认就移植到新固件。
- 中键被旧状态机用于切换，正常输出中始终屏蔽中键；新固件需明确是否保留这一用户体验。

## 新项目已验证的 Host 接口

`guobaren/ESP32-S3-HID-Bridge` 的 `host/HidBridge.Host/Automation/LuaScriptRunner.cs`：

- `mouse(button,state)`、`move(x,y)`、`sleep(ms)`、`IsPressed(arg)`、`OnEvent(event,arg)`。
- Host 事件通过 Windows `PhysicalInputEvent` 进入 Lua，不等价于 M 板 USB Host 实体鼠标输入。
- Lua `OnEvent` 在单 worker 上顺序执行；不宜依赖阻塞式循环实现需要即时响应的中键模式切换。
- 仅靠 Lua `mouse(1,0)` 无法保证覆盖双板透传的实体左键报告。

## 移植架构决定

优先将 **纯状态机**（输入按钮、tick、最终按钮掩码、Y 相对移动）与目标固件的 HID 报告生成/合并点连接。不要直接把旧 SPI `macpass_hid.c` 移植到 UART 工程。保留目标固件原始 HID 描述符与鼠标输入转发能力。

下一步必须取得目标 M/P 固件的 HID 输入、UART 协议、软件注入、USB 输出相关源码路径，并确认在 P 端能同时看到实体按钮状态与软件控制状态。此步骤完成前**不能安全修改目标固件**。

## 最低测试矩阵

1. 普通模式完整透传左右键、滚轮、侧键；中键切换是否占用按设计。
2. 炼狱随机边界与输出 press/release 配对；M4 50/100ms 与每轮下移3单位。
3. 实体左键保持按住时仍能生成真正的 release；松开后不会残留模拟按下。
4. 切换模式时先释放左键且要求重新按下；不重放 USB 阻塞期间过期边沿。
5. 断开 UART、USB 重连、复位和停止宏时恢复中性状态；右键和滚轮不受影响。
6. 视觉输入未来接入时可抢占宏，退出后状态可恢复。

结论：旧状态机可作为迁移核心，但 **P 端报告协调层**仍需目标工程源码级审计才能实施。
