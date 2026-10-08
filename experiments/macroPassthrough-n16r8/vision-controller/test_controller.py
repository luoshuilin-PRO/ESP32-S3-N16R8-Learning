"""Offline regression tests. No screenshot, serial opening, or HID output."""
import json
from pathlib import Path
import struct
import unittest
from unittest.mock import patch
import zlib
from PIL import Image
from detector import detect, DEFAULTS, Confirmation
from serial_link import packet, Link
from timing import FrameRate, validate_timing


class Tests(unittest.TestCase):
    def test_protocol(self):
        for cmd in (0,1,2):
            p=packet(123,cmd)
            self.assertEqual(len(p),16)
            self.assertEqual(p[:4],b'VC1!')
            self.assertEqual(p[8],cmd)
            self.assertEqual(struct.unpack('<I',p[12:])[0],zlib.crc32(p[:12]))

    def test_confirmation(self):
        c=Confirmation()
        self.assertFalse(c.update(True))
        self.assertTrue(c.update(True))
        self.assertFalse(c.update(False))
        self.assertFalse(c.update(True))

    def test_confirmation_choices_stop_and_restart(self):
        for frames in (1,2,3):
            c=Confirmation()
            for i in range(frames):
                self.assertEqual(c.update(True,frames),i==frames-1)
            self.assertTrue(c.update(True,frames))
            self.assertFalse(c.update(False,frames))
            for i in range(frames):
                self.assertEqual(c.update(True,frames),i==frames-1)

    def test_timing_settings(self):
        self.assertEqual(validate_timing('20','2'),(20,2))
        self.assertEqual(validate_timing(10,1),(10,1))
        self.assertEqual(validate_timing(100,3),(100,3))
        for interval,frames in [(0,2),(9,2),(101,2),(20,0),(20,4),('nan',2),(20,'1.5'),('',1)]:
            with self.assertRaises(ValueError):validate_timing(interval,frames)

    def test_actual_rate_includes_wait_and_stalls(self):
        rate=FrameRate()
        self.assertEqual(rate.record(0),0)
        self.assertAlmostEqual(rate.record(0.02),50)
        self.assertAlmostEqual(rate.record(0.04),50)
        self.assertAlmostEqual(rate.record(0.14),3/0.14)
        rate=FrameRate()
        for i in range(100):rate.record(i*0.01)
        self.assertEqual(len(rate.starts),60)
        self.assertAlmostEqual(rate.record(1),100)

    def test_uniform_backgrounds(self):
        for color in [(0,0,0),(123,44,67),(242,74,23),(0,255,0),(255,255,255)]:
            self.assertFalse(detect(Image.new('RGB',(84,25),color),DEFAULTS)['hit'])

    def test_all_samples(self):
        root=Path(__file__).resolve().parent.parent/'material-capture'/'samples'
        paths=list(root.rglob('*.png'))
        if not paths:
            self.skipTest('private image samples are not in the public repository')
        self.assertEqual(len(paths),23)
        for path in paths:
            # Labels corrected for evaluation only; original files are untouched.
            expected=path.parent.name!='negative' or '133728_410374' in path.name
            with Image.open(path) as image: result=detect(image,DEFAULTS)
            self.assertEqual(result['hit'],expected,str(path))

    def test_ack(self):
        class Port:
            def write(self,data):
                seq=struct.unpack('<I',data[4:8])[0]
                self.reply=f'boot log\nVC1 ACK {seq} {data[8]} 0\n'.encode()
            @property
            def in_waiting(self):return len(self.reply)
            def read(self,n):
                value,self.reply=self.reply[:n],self.reply[n:]; return value
        link=Link.__new__(Link); link.port=Port(); link.seq=10; link.buffer=b''
        self.assertFalse(link.exchange(0))

    def test_ack_timeout(self):
        class Port:
            in_waiting=0
            def write(self,data):pass
            def read(self,n):return b''
        link=Link.__new__(Link); link.port=Port(); link.seq=10; link.buffer=b''
        with self.assertRaises(TimeoutError):link.exchange(0,timeout=0.005)


if __name__=='__main__':unittest.main()
