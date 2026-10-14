"""红名素材与 V4 模拟协议回归，不打开设备。"""
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from red_detector import detect_red
from makcu_transport import Transport,V4Scanner
from test_output import FakePort


class Tests(unittest.TestCase):
    def test_material_pair(self):
        root=Path(__file__).parent/"samples"
        for name,expected in (("1791869812607756200-frame.png",True),("1791870144176117900-frame.png",False)):
            with self.subTest(name=name):
                result=detect_red(np.array(Image.open(root/name).convert("RGB")))
                self.assertEqual(result["hit"],expected)

    def test_wrong_resolution(self):
        with self.assertRaises(ValueError):
            detect_red(np.zeros((360,640,3),np.uint8))

    def test_all_red_rejected(self):
        self.assertFalse(detect_red(np.full((640,640,3),(255,0,0),np.uint8))["hit"])

    def test_v4_fragment_noise(self):
        scanner=V4Scanner()
        self.assertEqual(scanner.feed(b"log\xde"),[])
        self.assertEqual(scanner.feed(b"\xad\x01\x00\x55\x02"),[(0x55,b"\x02")])

    def test_v4_invalid_length(self):
        scanner=V4Scanner()
        self.assertEqual(scanner.feed(b"\xde\xad\xff\xff\x01"+b"\xde\xad\x01\x00\x55\x00"),[(0x55,b"\x00")])

    def test_raw_right_not_software(self):
        c=Transport(lambda _:None,FakePort)
        try:
            c.connect("FAKE",115200)
            self.assertTrue(c.right(c.physical_time))
            self.assertFalse(c.right(c.physical_time+.121))
            c.report(1,2,-3)
            self.assertEqual(c.port.writes[-1],b"\xde\xad\x04\x00\x18\x02\x00\xfd\xff")
            c.release()
            self.assertEqual(c.port.writes[-1],b"\xde\xad\x01\x00\x11\x00")
        finally:
            c.close()

    def test_query_timeout_invalidates(self):
        c=Transport(lambda _:None,FakePort)
        c.connect("FAKE",115200)
        with patch.object(c,"wire",return_value=None):
            with self.assertRaises(TimeoutError):
                c.poll_buttons()
        self.assertIsNone(c.physical_mask)
        c.close()

    def test_setter_no_success_ack_claim(self):
        c=Transport(lambda _:None,FakePort)
        c.connect("FAKE",115200)
        c.report(1,0,0)
        self.assertTrue(c.injected)
        c.close()
        self.assertFalse(c.injected)


if __name__=="__main__":
    unittest.main()
