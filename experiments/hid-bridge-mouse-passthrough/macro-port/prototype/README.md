# 独立宏状态机原型（未接入目标固件）

这是从旧 `macro_v1.c` 行为提取的纯 C 原型，不含 ESP-IDF、SPI、UART 或 TinyUSB 依赖。

**没有修改 HID-Bridge 固件，也没有执行烧录。** 当前只适合离线单元测试和接口审查。

编译测试（GCC/Clang）：

```sh
cc -std=c11 -Wall -Wextra -Werror macro_engine.c test_macro_engine.c -o test_macro_engine
./test_macro_engine
```

接口：
- `macro_engine_input`：输入真实鼠标的完整按钮位图，时间单位毫秒。
- `macro_engine_tick`：非阻塞地推进状态机；由调用方周期执行。
- `macro_engine_buttons`：输出最终按钮位图；必须在 HID 发送之前合并。
- `delta_y`：本次 tick 产生的 M4 下移量，消费后不要重复发送。
- `macro_engine_reset`：复位并要求先观察到全按键松开的报告。

注意：本原型保留左键接管和中键模式切换，默认不屏蔽侧键。与旧版视觉抢占逻辑尚未整合。设备端需要在 USB 提交成功后推进宏边沿或缓存待发送报告，防止丢失 press/release；此处没有实现 USB 报告队列。UART 中断、设备掉线时应调用 reset 并发送中性报告，不能只清空内存。
