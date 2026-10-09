"""VC1 CRC32 framing and synchronous acknowledgements. No queued click commands."""
import secrets
import struct
import time
import zlib
import serial


def packet(seq, command):
    """Encode STOP=0, fresh-frame grant=1, HELLO=2 into sixteen bytes."""
    body = struct.pack('<4sIB3x', b'VC1!', seq, command)
    return body + struct.pack('<I', zlib.crc32(body))


class Link:
    def __init__(self, port):
        self.port = serial.Serial(port=None, baudrate=115200, timeout=0.01, write_timeout=0.08)
        self.port.dtr = False
        self.port.rts = False
        self.port.port = port
        self.seq = secrets.randbelow(0x7fffffff)
        self.buffer = b''
        self.port.open()
        try:
            self.port.reset_input_buffer()
            self.exchange(2, timeout=1.0)
        except Exception:
            self.port.close()
            raise

    def exchange(self, command, timeout=0.12):
        """Wait for matching ACK; return whether native USB is configured."""
        self.seq = (self.seq + 1) & 0xffffffff
        started = time.perf_counter()
        self.port.write(packet(self.seq, command))
        self.last_write_done = time.perf_counter()
        self.last_write_ms = (self.last_write_done - started) * 1000
        deadline = time.monotonic() + timeout
        wanted = f'VC1 ACK {self.seq} {command} '.encode()
        while time.monotonic() < deadline:
            self.buffer += self.port.read(self.port.in_waiting or 1)
            while b'\n' in self.buffer:
                line, self.buffer = self.buffer.split(b'\n', 1)
                if line.startswith(wanted):
                    self.last_ack_ms = (time.perf_counter() - started) * 1000
                    return line[len(wanted):].strip() == b'1'
            if len(self.buffer) > 4096:
                self.buffer = b''
        raise TimeoutError('B 板没有及时确认 VC1 指令；已停止输出，请重新连接')

    def close(self):
        try:
            self.port.write(packet((self.seq+1) & 0xffffffff, 0))
        finally:
            self.port.close()
