"""HID-Bridge v0.1.2 的 A5/5A 协议子集，依据上游 bridge_protocol 与 UART0 实现。"""
import struct

MAGIC = b"\xa5\x5a"


def crc16(data):
    """输入字节，输出 CRC16-CCITT 整数；初值 FFFF，多项式 1021。"""
    crc = 0xFFFF
    for value in data:
        crc ^= value << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xFFFF
    return crc


def encode(kind, sequence, payload=b""):
    """输入消息类型、序号、载荷，输出完整线帧；拒绝超长载荷。"""
    if len(payload) > 64:
        raise ValueError("载荷超过 64 字节")
    body = struct.pack("<BBHB", 2, kind, sequence, len(payload)) + payload
    return MAGIC + body + struct.pack("<H", crc16(body))


class Scanner:
    """输入可能含日志、分片及坏 CRC 的字节流，返回有效 (类型, 序号, 载荷)。"""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        frames = []
        while True:
            start = self.buffer.find(MAGIC)
            if start < 0:
                self.buffer = self.buffer[-1:] if self.buffer[-1:] == MAGIC[:1] else bytearray()
                return frames
            del self.buffer[:start]
            if len(self.buffer) < 7:
                return frames
            size = self.buffer[6]
            if size > 64 or self.buffer[2] != 2:
                del self.buffer[:1]
                continue
            if len(self.buffer) < size + 9:
                return frames
            frame = bytes(self.buffer[:size + 9])
            if crc16(frame[2:-2]) != int.from_bytes(frame[-2:], "little"):
                del self.buffer[:1]
                continue
            del self.buffer[:size + 9]
            frames.append((frame[3], int.from_bytes(frame[4:6], "little"), frame[7:-2]))


def mouse(buttons=0, x=0):
    """输入软件按钮位和相对 X 位移，输出 8 字节报告；不使用平滑。"""
    return struct.pack("<BhhbbB", buttons, x, 0, 0, 0, 0)


class Snapshot:
    """输入统计分页，验证一致性并保存原始页；输出角色、uptime 与页完整性。"""
    def __init__(self):
        self.role = self.uptime = None
        self.counts = {}
        self.pages = {}

    def add(self, payload):
        if len(payload) < 12:
            raise ValueError("统计头不足")
        schema, role, kind, index, count, status, items, reserved, uptime = struct.unpack_from("<8BI", payload)
        length, maximum = (10, 5) if kind == 1 else (20, 2)
        if schema != 1 or role not in (1, 2) or kind not in (1, 2) or status or reserved:
            raise ValueError("统计 schema/角色/类别/状态错误")
        if not 0 <= index < count or not 1 <= items <= maximum or len(payload) != 12 + items * length:
            raise ValueError("统计页长度或页号错误")
        if self.role is not None and (self.role, self.uptime) != (role, uptime):
            raise ValueError("统计分页不是同一快照")
        if kind in self.counts and self.counts[kind] != count:
            raise ValueError("统计总页数变化")
        if (kind, index) in self.pages:
            raise ValueError("重复统计页")
        self.role, self.uptime = role, uptime
        self.counts[kind] = count
        self.pages[kind, index] = payload

    @property
    def complete(self):
        return all(kind in self.counts and sum(k == kind for k, _ in self.pages) == self.counts[kind]
                   for kind in (1, 2))
