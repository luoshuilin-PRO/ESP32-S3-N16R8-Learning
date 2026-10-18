"""已验证的 HID-Bridge 控制器适配＋纯状态机；默认不打开端口或注入输入。"""
from dataclasses import dataclass
import ctypes
import math
import queue
import struct
import sys
import threading
import time

from makcu_transport import Transport


@dataclass(frozen=True)
class Settings:
    click: bool = True
    move: bool = False
    press_ms: int = 50
    gap_ms: int = 100
    stale_ms: int = 200
    gain: float = .05
    max_step: int = 4
    radius: int = 150
    head_class: int = 1
    teammate_class: int = -1
    red_only: bool = False
    shift_hold: bool = False

    def validate(self):
        """核对输出参数范围，防止零间隔循环和无界位移。"""
        if not 10 <= self.press_ms <= 500 or not 10 <= self.gap_ms <= 1000:
            raise ValueError("按下／松开范围 10～500／10～1000ms")
        if not 80 <= self.stale_ms <= 500 or not .001 <= self.gain <= .25:
            raise ValueError("旧帧超时范围 80～500ms；移动比例 .001～.25")
        if not 1 <= self.max_step <= 10 or not 10 <= self.radius <= 1000:
            raise ValueError("单次步长 1～10；选择半径 10～1000 原视频像素")
        if self.head_class < 0 or self.teammate_class < -1 or self.head_class == self.teammate_class:
            raise ValueError("头部类别必须非负且不同于队友类别；队友 -1 表示不使用")


def eligible_heads(boxes, width, height, radius, head_class=1, teammate_class=-1):
    """返回范围内头部；与队友框相交的头部保守排除，包含敌友遮挡情况。"""
    friends = [b["box"] for b in boxes if b["class"] == teammate_class]
    result = []
    for item in boxes:
        if item["class"] != head_class:
            continue
        x1, y1, x2, y2 = item["box"]
        if math.hypot((x1+x2)/2-width/2, (y1+y2)/2-height/2) > radius:
            continue
        if any(min(x2, f[2]) > max(x1, f[0]) and min(y2, f[3]) > max(y1, f[1]) for f in friends):
            continue
        result.append(item)
    return result


def nearest_head(boxes, width, height, radius, head_class=1, teammate_class=-1):
    """输入检测框和原视频尺寸；返回准星范围内最近的 class=1 头部。"""
    cx, cy = width / 2, height / 2
    candidates = eligible_heads(boxes, width, height, radius, head_class, teammate_class)
    return min(candidates, key=lambda b: math.hypot(
        (b["box"][0]+b["box"][2])/2-cx,
        (b["box"][1]+b["box"][3])/2-cy)) if candidates else None


class Engine:
    """输入每次读取的最新检测与本地时间，输出软件按钮位／XY，不操作硬件。"""
    def __init__(self, settings):
        settings.validate()
        self.settings = settings
        self.reset()

    def reset(self):
        self.key = None
        self.misses = 0
        self.clicking = False
        self.origin = None
        self.move_key = None

    def step(self, result, now, right=False, click_allowed=True):
        """返回 (按钮,dx,dy,许可有效)；只统计新帧，过期直接撤销而非重复旧结果。"""
        cfg = self.settings
        if (not right and not cfg.red_only) or result is None or now - result["frame"].received > cfg.stale_ms / 1000:
            self.reset()
            return 0, 0, 0, False
        frame = result["frame"]
        height, width = frame.rgb.shape[:2]
        cx, cy = width / 2, height / 2
        key = (frame.stream, frame.sequence, result.get("epoch"))
        if self.key and key[0] != self.key[0]:
            self.reset()
        if not click_allowed:
            self.key = None
            self.clicking = False
            self.origin = None
            self.misses = 0
        fresh = click_allowed and key != self.key
        boxes = eligible_heads(result["boxes"], width, height, cfg.radius, cfg.head_class, cfg.teammate_class)
        if not boxes and not cfg.red_only:
            self.reset()
            return 0,0,0,False
        covered = bool(result.get("red",{}).get("hit",False))
        if fresh:
            self.key = key
            if covered and cfg.click and click_allowed:
                self.misses = 0
                if not self.clicking:
                    self.clicking = True
                    self.origin = now
            else:
                self.misses += 1
                if self.misses >= 3 or not cfg.click:
                    self.clicking = False
                    self.origin = None
        button = 0
        if self.clicking:
            period = (cfg.press_ms + cfg.gap_ms) / 1000
            button = int((now - self.origin) % period < cfg.press_ms / 1000)
        dx = dy = 0
        movable = False
        if cfg.move and right and boxes:
            candidates = []
            for item in boxes:
                x1,y1,x2,y2 = item["box"]
                tx,ty = (x1+x2)/2-cx, (y1+y2)/2-cy
                distance = math.hypot(tx,ty)
                if distance <= cfg.radius:
                    candidates.append((distance,tx,ty))
            if candidates:
                movable = True
                _,tx,ty = min(candidates)
                # 死区避免中心附近反复抖动；位移是 HID 单位，不是屏幕绝对像素。
                move_key = result.get("boxes_key", key)
                if move_key != self.move_key:
                    self.move_key = move_key
                    dx = 0 if abs(tx) < 3 else round(max(-cfg.max_step,min(cfg.max_step,tx*cfg.gain)))
                    dy = 0 if abs(ty) < 3 else round(max(-cfg.max_step,min(cfg.max_step,ty*cfg.gain)))
        return button, dx, dy, self.clicking or movable


class Output:
    """单线程独占串口，GUI 仅提交任务；紧急事件在任务之外立即撤销许可。"""
    def __init__(self, get_result, notify, factory=None, get_red_result=None):
        self.get_result, self.notify = get_result, notify
        self.get_red_result = get_red_result or get_result
        self.controller = Transport(lambda _: None, **({"factory":factory} if factory else {}))
        self.jobs = queue.Queue()
        self.halt = threading.Event()
        self.quitting = threading.Event()
        self.armed = False
        self.engine = Engine(Settings())
        self.last_buttons = None
        self.last_write = 0
        self.last_poll = 0
        self.last_mask = None
        self.thread = threading.Thread(target=self.run, daemon=False)
        self.thread.start()

    def request(self, action, value=None):
        self.jobs.put((action,value))

    def stop(self):
        """撤销输出许可；恢复需再次由用户确认，不自动重新武装。"""
        self.halt.set()

    def close(self):
        self.halt.set()
        self.quitting.set()

    def emergency_key(self):
        """Windows 全局 F8 只读查询，不生成任何系统输入。"""
        return sys.platform == "win32" and bool(ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000)

    def shift_key(self):
        """只读查询运行本程序的 Windows 电脑上的 Shift 键。"""
        return sys.platform == "win32" and bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)

    def release(self):
        self.controller.release()
        self.last_buttons = None

    def drain_rx(self):
        """持续消费混合日志，避免自动输出期间接收缓冲无界累积。"""
        port = self.controller.port
        if port and port.in_waiting:
            for kind,payload in self.controller.frames(port.read(min(port.in_waiting,4096))):
                raise RuntimeError(f"非预期响应 0x{kind:02X}，重新连接")

    def run(self):
        try:
            while not self.quitting.wait(.003):
                try:
                    if self.halt.is_set() or self.emergency_key():
                        if self.armed:
                            self.armed = False
                            self.release()
                            self.engine.reset()
                            self.notify(("output_armed",False))
                        # 事件保留到新的明确 arm 请求；不会在新动作开始前丢失停止。
                    try:
                        action,value = self.jobs.get_nowait()
                    except queue.Empty:
                        action = None
                    if action == "connect":
                        self.armed = False
                        self.controller.connect(value,115200)
                        self.notify(("output_connected",True))
                        self.notify("M 板／V4 已确认，正在只读轮询真实按钮；输出仍关闭")
                    elif action == "disconnect":
                        self.armed = False
                        self.controller.close()
                        self.notify(("output_connected",False))
                        self.notify(("output_armed",False))
                    elif action == "arm":
                        if self.armed:
                            self.notify("输出已启用；修改配置前请先停止输出")
                            continue
                        value.validate()
                        if self.controller.verify() != 2:
                            raise RuntimeError("重新核对 M 板角色失败")
                        # 查询等待期间仍可停止，禁止在停止/退出后重新启用。
                        if self.halt.is_set() or self.quitting.is_set():
                            self.notify("启用已取消，请再次明确启用")
                            continue
                        sample = (self.get_red_result if value.red_only else self.get_result)()
                        if sample is None or time.monotonic()-sample["frame"].received > value.stale_ms/1000:
                            self.notify("启用取消：没有新鲜识别结果")
                            continue
                        self.engine = Engine(value)
                        self.armed = True
                        self.notify(("output_armed",True))
                    self.drain_rx()
                    needs_buttons = not self.armed or not self.engine.settings.red_only or self.engine.settings.move
                    if self.controller.port and needs_buttons and time.monotonic()-self.last_poll >= .02:
                        query_start = time.monotonic()
                        self.controller.poll_buttons()
                        self.last_poll=time.monotonic()
                        mask=self.controller.physical_mask
                        if self.last_poll-getattr(self,"last_timing",0) >= .5:
                            self.last_timing=self.last_poll
                            self.notify(("physical_timing",mask,(self.last_poll-query_start)*1000))
                        if mask != self.last_mask:
                            self.last_mask=mask
                            self.notify(("physical",mask))
                    if not self.armed:
                        continue
                    if not self.engine.settings.red_only and not self.controller.right(time.monotonic()):
                        if self.controller.injected:
                            self.release()
                        self.engine.reset()
                        continue
                    sample = (self.get_red_result if self.engine.settings.red_only else self.get_result)()
                    if sample is None or time.monotonic()-sample["frame"].received > self.engine.settings.stale_ms/1000:
                        self.armed = False
                        self.release()
                        self.notify(("output_armed",False))
                        self.notify("输出已关闭：断流或识别结果过期；恢复后需再次启用")
                        continue
                    shift_required = self.engine.settings.red_only and self.engine.settings.shift_hold
                    click_allowed = not shift_required or self.shift_key()
                    button,dx,dy,valid = self.engine.step(
                        sample,time.monotonic(),right=self.controller.right(time.monotonic()),
                        click_allowed=click_allowed)
                    if not valid:
                        if self.controller.injected:
                            self.release()
                        continue
                    now = time.monotonic()
                    if button != self.last_buttons or dx or dy or now-self.last_write >= .1:
                        # 会话与每次写入之间再次检查停止，finally 负责释放。
                        if self.halt.is_set() or self.quitting.is_set():
                            continue
                        if not self.engine.settings.red_only and not self.controller.right(time.monotonic()):
                            continue
                        if button and shift_required and not self.shift_key():
                            self.engine.clicking = False
                            self.engine.origin = None
                            self.release()
                            continue
                        self.controller.report(button,dx,dy)
                        self.last_buttons,self.last_write = button,now
                except Exception as error:
                    self.armed = False
                    self.halt.set()
                    self.notify(f"串口输出停止：{error}")
                    try:
                        self.controller.close()
                    except Exception as cleanup:
                        self.notify(f"释放未确认到达：{cleanup}；请检查主机按钮状态")
                    self.notify(("output_connected",False))
                    self.notify(("output_armed",False))
        finally:
            try:
                self.controller.close()
            except Exception as error:
                self.notify(f"退出释放失败：{error}；请检查主机")
