"""不连接网络或输入硬件的核心回归。"""
import unittest
import threading
from unittest.mock import patch
import numpy as np
from core import Latest, fit, selection, crop_rect, ndi_rgb
from detector import letterbox, parse_output


class Tests(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(fit(1920,1080,1000,1000),(1000,562,0,219))

    def test_roi_full(self):
        self.assertEqual(selection((0,0),(1000,1000),(1920,1080),(1000,1000)),(0,0,1920,1080))

    def test_roi_reverse(self):
        self.assertEqual(selection((80,80),(20,20),(100,100),(100,100)),(20,20,60,60))

    def test_roi_black(self):
        self.assertIsNone(selection((0,0),(100,100),(1920,1080),(1000,1000)))

    def test_out_of_bounds(self):
        with self.assertRaises(ValueError):
            crop_rect((90,0,20,20),100,100)

    def test_latest(self):
        q = Latest()
        for i in range(1000):
            q.put(i)
        self.assertEqual(q.get(),999)
        q.put(None)
        self.assertIsNone(q.get())

    def test_latest_threads(self):
        q = Latest()
        threads = [threading.Thread(target=lambda: [q.put(i) for i in range(100)]) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(q.get(),99)

    def test_stride(self):
        raw = bytes([1,2,3,255,4,5,6,255,9,9,9,9]*2)
        rgb = ndi_rgb(raw,2,2,12,"RGBA")
        self.assertEqual(rgb.tolist(), [[[1,2,3],[4,5,6]]]*2)

    def test_bgra(self):
        self.assertEqual(ndi_rgb(bytes([1,2,3,255]),1,1,4,"BGRA").tolist(),[[[3,2,1]]])

    def test_stride_error(self):
        with self.assertRaises(ValueError):
            ndi_rgb(bytes(4),2,1,4,"RGBA")

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            ndi_rgb(bytes(4),1,1,4,"UYVY")

    def test_letterbox(self):
        a, transform = letterbox(np.zeros((100,200,3),np.uint8),320,320)
        self.assertEqual(a.shape,(1,3,320,320))
        self.assertEqual(transform,(1.6,0,80))

    def parse(self, data, layout="v5", allowed=set()):
        return parse_output(np.array(data,dtype=np.float32),layout,2,.25,.45,(1,0,0),(100,100),allowed)

    def test_v5_nms(self):
        output = [[[50,50,20,20,.9,.9,.1],[50,50,20,20,.8,.9,.1]]]
        boxes = self.parse(output)
        self.assertEqual(len(boxes),1)
        self.assertEqual(boxes[0]["box"],[40,40,60,60])
        self.assertAlmostEqual(boxes[0]["score"],.81,places=5)

    def test_class_filter(self):
        self.assertEqual(self.parse([[[50,50,20,20,.9,.9,.1]]],allowed={1}),[])

    def test_v8(self):
        boxes = self.parse([[[50],[50],[20],[20],[.9],[.1]]],"v8")
        self.assertEqual(len(boxes),1)

    def test_xyxy(self):
        boxes = self.parse([[[1,2,20,30,.8,1]]],"xyxy")
        self.assertEqual(boxes[0]["class"],1)

    def test_wrong_layout(self):
        with self.assertRaises(ValueError):
            self.parse([[[1,2,3]]])

    def test_letterbox_inverse(self):
        boxes = parse_output(np.array([[[160,160,32,32,.9,.9,.1]]],np.float32),"v5",2,.25,.45,
                             (1.6,0,80),(200,100),set())
        self.assertEqual(boxes[0]["box"],[90,40,110,60])

    def test_nonfinite(self):
        self.assertEqual(self.parse([[[float('nan'),50,20,20,.9,.9,.1]]]),[])

    def test_disconnect_missing_source(self):
        from ndi_input import receive
        class Finder:
            def __enter__(self):
                return self
            def __exit__(self,*args):
                pass
            def wait_for_sources(self,timeout):
                pass
            def get_source(self,name):
                return None
        with patch("ndi_input.Finder",Finder):
            with self.assertRaises(RuntimeError):
                receive("missing",threading.Event(),Latest(),lambda _:None,1)

    def test_receive_disconnect_recovery(self):
        from ndi_input import receive
        from cyndilib.receiver import ReceiveFrameType
        stop = threading.Event()
        history, statuses = [], []
        class Sink:
            def put(self, item):
                history.append(item)
        class Finder:
            def __enter__(self):
                return self
            def __exit__(self,*args):
                pass
            def wait_for_sources(self,timeout):
                pass
            def get_source(self,name):
                return object()
        class Video(bytearray):
            def __init__(self,**kwargs):
                super().__init__(bytes([1,2,3,255]))
                self.xres = self.yres = 1
            def get_buffer_depth(self):
                return 1
            def skip_frames(self,**kwargs):
                raise AssertionError("单帧不应跳过")
            def get_line_stride(self):
                return 4
            def get_fourcc(self):
                return type("Format",(),{"name":"RGBA"})()
        class Receiver:
            disconnected = False
            def __init__(self,**kwargs):
                self.calls = 0
            def set_video_frame(self,frame):
                pass
            def set_source(self,source):
                pass
            def receive(self,kind,timeout):
                self.calls += 1
                if self.calls >= 16:
                    stop.set()
                return ReceiveFrameType.recv_video if self.calls in (1,12) else ReceiveFrameType.nothing
            def reconnect(self):
                pass
            def disconnect(self):
                Receiver.disconnected = True
        clock = iter(i*.4 for i in range(100))
        with patch("ndi_input.Finder",Finder), patch("ndi_input.Receiver",Receiver), \
                patch("ndi_input.VideoRecvFrame",Video), patch("ndi_input.time.monotonic",side_effect=lambda:next(clock)):
            receive("fake",stop,Sink(),statuses.append,1)
        self.assertEqual([x.sequence for x in history if x is not None],[1,2])
        self.assertGreater(sum(x is None for x in history),0)
        self.assertTrue(any(isinstance(s,str) and "断流" in s for s in statuses))
        self.assertTrue(Receiver.disconnected)


if __name__ == "__main__":
    unittest.main()
