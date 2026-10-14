"""模拟串口和协议异常，不打开真实设备、不发送 HID。"""
import struct
import threading
import unittest
from unittest.mock import patch
from controller import Controller
from protocol import Scanner, Snapshot, crc16, encode, mouse


class FakePort:
    def __init__(self, **kwargs):
        self.is_open = False
        self.dtr = self.rts = True
        self.writes = []
        self.rx = b""
        self.short = False
        self.fail_at = None

    def open(self):
        assert not self.dtr and not self.rts
        self.is_open = True

    def write(self, data):
        self.writes.append(data)
        if len(self.writes) == self.fail_at:
            raise OSError("模拟断线")
        if data[3] == 6:
            self.rx += encode(7, int.from_bytes(data[4:6], "little"), b"HIDBRDG2" + data[7:-2] + b"\x02")
        return len(data) - 1 if self.short else len(data)

    def read(self, size):
        result, self.rx = self.rx[:size], self.rx[size:]
        return result

    def close(self):
        self.is_open = False


class Tests(unittest.TestCase):
    def controller(self):
        c = Controller(lambda _: None, FakePort)
        c.connect("FAKE", 115200)
        return c

    def test_crc(self):
        self.assertEqual(crc16(b"123456789"), 0x29B1)

    def test_fragment_and_noise(self):
        scanner = Scanner()
        frame = encode(7, 65535, b"hello")
        self.assertEqual(scanner.feed(b"log\n" + frame[:1]), [])
        self.assertEqual(scanner.feed(frame[1:]), [(7, 65535, b"hello")])

    def test_bad_crc_resync(self):
        good = encode(4, 1)
        bad = good[:-1] + bytes([good[-1] ^ 1])
        self.assertEqual(Scanner().feed(bad + good), [(4, 1, b"")])

    def test_payload_limit(self):
        with self.assertRaises(ValueError):
            encode(1, 1, bytes(65))

    def test_mouse_layout(self):
        self.assertEqual(mouse(x=-4), bytes.fromhex("00 fc ff 00 00 00 00 00"))

    def test_open_no_input(self):
        c = self.controller()
        port = c.port
        self.assertFalse(port.dtr or port.rts)
        c.close()
        self.assertEqual(port.writes, [])

    def test_probe(self):
        c = self.controller()
        self.assertEqual(c.probe(), 2)
        self.assertEqual(len(c.port.writes), 1)
        c.close()

    def test_nonce_and_sequence_rejected(self):
        c = self.controller()
        with patch.object(c, "responses", return_value=iter([(7, 999, b"HIDBRDG2" + bytes(8) + b"\x02")])):
            with self.assertRaises(TimeoutError):
                c.probe()
        self.assertIsNone(c.role)
        c.close()

    def test_role_guard(self):
        c = self.controller()
        c.role = 1
        with self.assertRaises(RuntimeError):
            c.test("click", threading.Event())
        self.assertEqual(c.port.writes, [])
        c.close()

    def test_click_release(self):
        c = self.controller()
        c.role = 2
        c.test("click", threading.Event())
        reports = [f[7:-2] for f in c.port.writes if f[3] == 2]
        self.assertEqual([r[0] for r in reports], [1, 0])
        self.assertEqual(c.port.writes[-1][3], 3)
        c.close()

    def test_stop_before_input(self):
        c = self.controller()
        c.role = 2
        stop = threading.Event()
        stop.set()
        c.test("move", stop)
        self.assertEqual(c.port.writes, [])
        c.close()

    def test_stop_during_move(self):
        c = self.controller()
        c.role = 2
        class Stop:
            def is_set(self):
                return False
            def wait(self, seconds):
                return True
        c.test("move", Stop())
        reports = [f[7:-2] for f in c.port.writes if f[3] == 2]
        self.assertEqual(reports, [mouse(x=4), mouse()])
        c.close()

    def test_short_write(self):
        c = self.controller()
        c.port.short = True
        with self.assertRaises(OSError):
            c.probe()
        c.close()

    def test_release_after_error(self):
        c = self.controller()
        c.role = 2
        c.port.fail_at = 2
        with self.assertRaises(OSError):
            c.test("click", threading.Event())
        self.assertEqual(c.port.writes[-1][3], 3)
        c.close()

    def test_snapshot_pages(self):
        s = Snapshot()
        for kind, record in ((1, bytes(10)), (2, bytes(20))):
            s.add(struct.pack("<8BI", 1, 2, kind, 0, 1, 0, 1, 0, 1234) + record)
        self.assertTrue(s.complete)
        self.assertEqual(s.uptime, 1234)
        with self.assertRaises(ValueError):
            s.add(struct.pack("<8BI", 1, 2, 1, 0, 1, 0, 1, 0, 1234) + bytes(10))

    def test_snapshot_mixed_uptime(self):
        s = Snapshot()
        s.add(struct.pack("<8BI", 1, 2, 1, 0, 1, 0, 1, 0, 10) + bytes(10))
        with self.assertRaises(ValueError):
            s.add(struct.pack("<8BI", 1, 2, 2, 0, 1, 0, 1, 0, 20) + bytes(20))


if __name__ == "__main__":
    unittest.main()
