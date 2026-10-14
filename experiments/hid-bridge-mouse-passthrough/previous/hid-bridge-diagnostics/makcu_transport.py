"""HID-Bridge v0.1.2 已核对 V4 子集；身份确认后不再交替切换 A5。"""
import struct
import time
from pathlib import Path
import sys

from controller import Controller


class V4Scanner:
    """输入混合字节流，返回长度校验通过的 (opcode,payload)，限制缓冲长度。"""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self,data):
        self.buffer.extend(data)
        result=[]
        while True:
            start=self.buffer.find(b"\xde\xad")
            if start<0:
                self.buffer=self.buffer[-1:] if self.buffer[-1:]==b"\xde" else bytearray()
                return result
            del self.buffer[:start]
            if len(self.buffer)<5:
                return result
            size=int.from_bytes(self.buffer[2:4],"little")
            if size>64:
                del self.buffer[:1]
                continue
            if len(self.buffer)<5+size:
                return result
            result.append((self.buffer[4],bytes(self.buffer[5:5+size])))
            del self.buffer[:5+size]


class Transport(Controller):
    """沿用无复位打开和 A5 身份确认，运行期只用 V4，查询超时即撤销资格。"""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.v4=False
        self.v4_scanner=V4Scanner()
        self.physical_mask=None
        self.physical_time=0

    def connect(self,name,baud):
        super().connect(name,baud)
        self.v4=False
        self.physical_mask=None
        self.physical_time=0
        self.v4_scanner=V4Scanner()
        if super().probe()!=2:
            raise RuntimeError("A5 身份不是 M 板")
        self.port.timeout=.005
        self.v4=True
        self.verify()

    def wire(self,opcode,payload=b""):
        """只写一条已核对的 V4 帧；SET 没有成功 ACK，禁止伪造确认。"""
        data=b"\xde\xad"+struct.pack("<H",len(payload))+bytes([opcode])+payload
        if self.port is None or not self.port.is_open or self.port.write(data)!=len(data):
            raise OSError("V4 写入失败或短写")

    def frames(self,data):
        for opcode,payload in self.v4_scanner.feed(data):
            if payload==b"\xff":
                raise RuntimeError(f"V4 命令拒绝 0x{opcode:02X}")
            if opcode==0x53:
                raise RuntimeError("收到非本工具的订阅事件；请停止其他串口客户端并重新连接")
            yield opcode,payload

    def query(self,opcode):
        """单个在途查询，无重试；超时关闭资格，避免迟到响应冒充新鲜状态。"""
        self.wire(opcode)
        deadline=time.monotonic()+.08
        while time.monotonic()<deadline:
            for kind,payload in self.frames(self.port.read(self.port.in_waiting or 1)):
                if kind==opcode:
                    return payload
                raise RuntimeError(f"收到不匹配 V4 响应 0x{kind:02X}")
        self.physical_mask=None
        self.physical_time=0
        raise TimeoutError("V4 查询超时，右键状态失效")

    def verify(self):
        if self.query(0x04)!=struct.pack("<I",4):
            raise RuntimeError("V4 API 握手不匹配")
        self.poll_buttons()
        return self.role

    def poll_buttons(self):
        payload=self.query(0x55)
        if len(payload)!=1 or payload[0]>31:
            raise ValueError("物理按钮掩码非法")
        self.physical_mask=payload[0]
        self.physical_time=time.monotonic()
        return bool(payload[0]&2)

    def right(self,now):
        return self.physical_mask is not None and now-self.physical_time <= .12 and bool(self.physical_mask&2)

    def report(self,button,dx,dy):
        """输出左键状态及限幅相对移动；不屏蔽物理按钮，不改变插值设置。"""
        if self.role!=2 or not self.v4:
            raise RuntimeError("未验证 V4 M 板")
        self.injected=True
        self.wire(0x11,bytes([button]))
        if dx or dy:
            self.wire(0x18,struct.pack("<hh",dx,dy))

    def release(self):
        if not self.v4:
            return super().release()
        if self.injected:
            self.wire(0x11,b"\x00")
            self.injected=False
            self.log("V4 左键释放已写入，非目标端确认")

    def close(self):
        try:
            super().close()
        finally:
            self.physical_mask=None
            self.physical_time=0
