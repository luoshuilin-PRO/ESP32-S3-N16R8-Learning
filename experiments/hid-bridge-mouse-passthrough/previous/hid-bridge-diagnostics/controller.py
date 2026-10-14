"""独占串口控制器；不自动连接、不自动输入、不切换波特率。"""
import secrets
import time
import serial
from protocol import Scanner, Snapshot, encode, mouse


class Controller:
    """输入日志回调及串口工厂，执行串行操作；由界面单个后台线程拥有。"""
    def __init__(self, log, factory=None):
        self.log, self.factory = log, factory or serial.Serial
        self.port = None
        self.sequence = 0
        self.role = None
        self.injected = False
        self.previous_uptime = None
        self.previous_time = None
        self.scanner = Scanner()

    def connect(self, name, baud):
        """输入端口及手动选定波特率，打开端口并保持 DTR/RTS 低；无输出输入报告。"""
        self.close()
        self.role = None
        self.previous_uptime = self.previous_time = None
        self.scanner = Scanner()
        port = self.factory(port=None, baudrate=baud, timeout=0.05, write_timeout=0.5,
                            rtscts=False, dsrdtr=False)
        port.dtr = False
        port.rts = False
        port.port = name
        try:
            port.open()
            port.dtr = False
            port.rts = False
        except Exception:
            port.close()
            raise
        self.port = port
        self.log(f"已打开 {name} / {baud}；尚未验证设备，未发送输入")

    def send(self, kind, payload=b""):
        """输入协议类型与载荷，输出使用的序号；写入成功不代表电脑消费。"""
        if self.port is None or not self.port.is_open:
            raise OSError("串口未连接")
        sequence = self.sequence
        self.sequence = (sequence + 1) & 0xFFFF
        frame = encode(kind, sequence, payload)
        if self.port.write(frame) != len(frame):
            raise OSError("串口写入不完整")
        self.log(f"TX {frame.hex(' ')}；串口写入完成（非 HID 确认）")
        return sequence

    def responses(self, seconds):
        """输入最长等待秒数，逐个返回合法协议帧并记录原始接收内容。"""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            data = self.port.read(4096)
            if data:
                self.log(f"RX {data.hex(' ')}")
                yield from self.scanner.feed(data)

    def probe(self):
        """发送 nonce 身份查询，验证签名、序号和角色；失败立即撤销输入资格。"""
        self.role = None
        nonce = secrets.token_bytes(8)
        sequence = self.send(0x06, nonce)
        for kind, seq, payload in self.responses(1.5):
            if kind == 0x07 and seq == sequence and len(payload) == 17 and payload[:16] == b"HIDBRDG2" + nonce:
                self.role = payload[16]
                self.log(f"身份响应有效；角色={self.role}（2=M，1=P，0=未定）；此字段不含固件版本")
                return self.role
        raise TimeoutError("身份查询超时；检查端口、波特率和其他占用程序，未发送鼠标输入")

    def stats(self):
        """查询完整统计分页；比较 uptime 与墙钟，返回完整快照，无输入报告。"""
        snapshot = Snapshot()
        sequence = self.send(0x1D)
        for kind, seq, payload in self.responses(3):
            if kind == 0x1E and seq == sequence:
                snapshot.add(payload)
                if snapshot.complete:
                    now = time.monotonic()
                    if self.previous_uptime is None:
                        self.log(f"uptime={snapshot.uptime}ms：首次基线，单次查询不证明未复位")
                    else:
                        delta = snapshot.uptime - self.previous_uptime
                        wall = (now - self.previous_time) * 1000
                        continuous = delta >= 0 and abs(delta - wall) < 1500
                        self.log(f"uptime={snapshot.uptime}ms；增量={delta}ms，墙钟={wall:.0f}ms；连续={continuous}")
                        if not continuous:
                            self.role = None
                            raise RuntimeError("uptime 异常；输入资格撤销，请重新核对设备")
                    self.previous_uptime, self.previous_time = snapshot.uptime, now
                    self.log(f"统计分页完整，角色={snapshot.role}；这不是鼠标命令 ACK")
                    return snapshot
        raise TimeoutError("统计快照缺页或超时")

    def test(self, action, stop):
        """输入用户确认的 move/click 和停止事件，执行一次动作；finally 释放软件按钮。"""
        if action not in ("move", "click"):
            raise ValueError("未知测试动作")
        if self.role != 2:
            raise RuntimeError("只允许已验证的 MOUSE_HOST 执行输入")
        if stop.is_set():
            return
        self.injected = True
        try:
            self.send(0x05)
            if stop.is_set():
                return
            self.send(0x02, mouse(x=4) if action == "move" else mouse(buttons=1))
            cancelled = stop.wait(0.25 if action == "move" else 0.05)
            if action == "move" and not cancelled:
                self.send(0x02, mouse(x=-4))
            self.log("动作写入结束；请在主机确认实际效果，协议没有该动作的逐条 HID ACK")
        finally:
            self.release()

    def release(self):
        """仅在本工具发起过输入时尝试释放；断线时报告失败而不伪造成功。"""
        if self.injected:
            try:
                self.send(0x02, mouse())
                self.send(0x03)
                self.injected = False
                self.log("软件按钮释放命令已写入；目标实际释放需观察")
            except Exception as error:
                self.role = None
                self.log(f"释放发送失败：{error}；请在主机检查按钮状态，不保证释放到达")
                raise

    def close(self):
        """释放本工具输入并关闭端口，纯查询连接不会发送释放帧。"""
        try:
            self.release()
        finally:
            if self.port is not None:
                self.port.close()
            self.port = None
            self.role = None
            self.injected = False
