"""Tkinter 手动串口测试界面；所有设备操作通过单一后台线程串行执行。"""
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from pathlib import Path
from serial.tools import list_ports
from controller import Controller


class App:
    def __init__(self, root):
        """输入 Tk 根窗口，创建默认只读界面；不打开串口。"""
        self.root = root
        root.title("HID-Bridge 串口测试")
        root.geometry("920x600")
        root.minsize(760, 450)
        self.events, self.jobs = queue.Queue(), queue.Queue()
        self.stop = threading.Event()
        self.closing = self.busy = False
        self.connected = False
        self.role = None
        self.controller = Controller(lambda text: self.events.put(("log", text)))
        self.log_path = Path(__file__).parent / "logs"
        self.log_path.mkdir(exist_ok=True)
        self.log_file = (self.log_path / time.strftime("session-%Y%m%d-%H%M%S.log")).open("a", encoding="utf-8")
        top = ttk.Frame(root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="串口").pack(side="left")
        self.port = ttk.Combobox(top, width=13, state="readonly")
        self.port.pack(side="left", padx=6)
        ttk.Button(top, text="刷新", command=self.refresh).pack(side="left")
        ttk.Label(top, text="波特率").pack(side="left", padx=(16, 4))
        self.baud = ttk.Combobox(top, values=(115200, 921600), width=10, state="readonly")
        self.baud.set(115200)
        self.baud.pack(side="left")
        self.connect_button = ttk.Button(top, text="连接", command=self.connect)
        self.connect_button.pack(side="left", padx=8)
        self.disconnect_button = ttk.Button(top, text="断开", command=self.disconnect)
        self.disconnect_button.pack(side="left")
        commands = ttk.Frame(root, padding=(10, 0, 10, 10))
        commands.pack(fill="x")
        self.probe_button = ttk.Button(commands, text="查询身份", command=lambda: self.submit("probe"))
        self.stats_button = ttk.Button(commands, text="读取统计", command=lambda: self.submit("stats"))
        self.move_button = ttk.Button(commands, text="右移／左移", command=lambda: self.confirm("move"))
        self.click_button = ttk.Button(commands, text="左键单击", command=lambda: self.confirm("click"))
        for button in (self.probe_button, self.stats_button, self.move_button, self.click_button):
            button.pack(side="left", padx=(0, 8))
        ttk.Button(commands, text="停止", command=self.stop.set).pack(side="left")
        self.status = tk.StringVar(value="未连接")
        ttk.Label(root, textvariable=self.status, padding=(10, 0, 10, 8)).pack(anchor="w")
        self.output = scrolledtext.ScrolledText(root, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()
        self.controls()
        self.thread = threading.Thread(target=self.worker, daemon=False)
        self.thread.start()
        root.after(50, self.poll)

    def refresh(self):
        """枚举端口但不打开；输出清单到下拉框。"""
        if self.busy or self.connected:
            return
        self.port["values"] = [p.device for p in list_ports.comports()]
        self.port.set("")

    def controls(self):
        """依据连接、角色及忙碌状态更新控件，不发送设备指令。"""
        idle = not self.busy and not self.closing
        self.connect_button["state"] = "normal" if idle and not self.connected else "disabled"
        self.disconnect_button["state"] = "normal" if idle and self.connected else "disabled"
        for button in (self.probe_button, self.stats_button):
            button["state"] = "normal" if idle and self.connected else "disabled"
        for button in (self.move_button, self.click_button):
            button["state"] = "normal" if idle and self.connected and self.role == 2 else "disabled"
        self.port["state"] = self.baud["state"] = "readonly" if idle and not self.connected else "disabled"

    def submit(self, action, args=()):
        """提交一个串行任务；忙碌期间拒绝第二个任务，避免重复点击。"""
        if self.busy or self.closing:
            return
        self.busy = True
        self.stop.clear()
        self.controls()
        self.jobs.put((action, args))

    def connect(self):
        if not self.port.get():
            messagebox.showwarning("串口", "请先选择 A 板串口")
            return
        self.submit("connect", (self.port.get(), int(self.baud.get())))

    def disconnect(self):
        self.submit("disconnect")

    def confirm(self, action):
        """每次移动或点击单独确认，确认后才向工作线程提交动作。"""
        name = "右移 4 个相对单位后左移 4 个单位" if action == "move" else "左键单击一次"
        if messagebox.askyesno("确认实机输入", f"请在主机打开空白测试窗口，松开物理鼠标按钮。\n\n现在执行：{name}？"):
            self.submit(action)

    def worker(self):
        """唯一串口拥有线程，返回日志及状态；失败关闭串口并撤销输入资格。"""
        while True:
            action, args = self.jobs.get()
            try:
                if action == "quit":
                    self.controller.close()
                    return
                if action == "connect":
                    self.controller.connect(*args)
                elif action == "disconnect":
                    self.controller.close()
                elif action == "probe":
                    self.controller.probe()
                elif action == "stats":
                    self.controller.stats()
                else:
                    self.controller.test(action, self.stop)
            except Exception as error:
                self.events.put(("log", f"错误：{error}"))
                try:
                    self.controller.close()
                except Exception as cleanup:
                    self.events.put(("log", f"关闭时释放失败：{cleanup}"))
                if action == "quit":
                    return
            finally:
                self.events.put(("done", (self.controller.port is not None, self.controller.role)))

    def poll(self):
        """将后台结果交给 Tk 主线程，追加时间戳日志并完成关闭。"""
        while not self.events.empty():
            kind, value = self.events.get()
            if kind == "log":
                line = time.strftime("%H:%M:%S") + " " + value + "\n"
                self.log_file.write(line)
                self.log_file.flush()
                self.output.configure(state="normal")
                self.output.insert("end", line)
                self.output.see("end")
                self.output.configure(state="disabled")
            else:
                self.connected, self.role = value
                self.busy = False
                self.status.set(f"{'已连接' if self.connected else '未连接'}；角色={self.role if self.role is not None else '未验证'}")
                self.controls()
        if self.closing and not self.thread.is_alive():
            self.log_file.close()
            self.root.destroy()
            return
        self.root.after(50, self.poll)

    def close(self):
        """停止待执行输入，排队释放和断开，等待工作线程退出后销毁窗口。"""
        if not self.closing:
            self.closing = True
            self.stop.set()
            self.controls()
            self.jobs.put(("quit", ()))


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
