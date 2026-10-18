"""Red-only regression tests use synthetic frames; no hardware output."""
import unittest
import threading
import time
import importlib.util
from pathlib import Path
from unittest.mock import patch
import numpy as np
from core import Latest, Frame
from red_detector import RedSettings
from output_control import Engine, Settings
from output_control import Output
from test_output import sample, FakePort

spec = importlib.util.spec_from_file_location('ndi_viewer_main_test', Path(__file__).with_name('main.py'))
viewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(viewer)
App = viewer.App


class RedOnlyTests(unittest.TestCase):
    def test_shift_gate_releases_and_restarts_on_new_frame(self):
        engine = Engine(Settings(red_only=True, shift_hold=True))
        self.assertEqual(engine.step(sample(1, []), 0, click_allowed=False), (0, 0, 0, False))
        self.assertEqual(engine.step(sample(2, [], .01), .01, click_allowed=True)[0], 1)
        self.assertEqual(engine.step(sample(2, [], .01), .02, click_allowed=False), (0, 0, 0, False))
        self.assertEqual(engine.step(sample(3, [], .03), .03, click_allowed=True)[0], 1)

    def test_shift_gate_does_not_disable_independent_movement(self):
        engine = Engine(Settings(red_only=True, shift_hold=True, move=True))
        button, dx, dy, valid = engine.step(sample(1, [[70, 70, 90, 90]]), 0,
                                            right=True, click_allowed=False)
        self.assertEqual(button, 0)
        self.assertTrue(valid)
        self.assertNotEqual((dx, dy), (0, 0))

    def test_no_right_no_boxes_first_hit(self):
        engine = Engine(Settings(red_only=True))
        self.assertEqual(engine.step(sample(1, []), 0, right=False), (1,0,0,True))

    def test_head_loss_does_not_interrupt_click_cycle(self):
        engine = Engine(Settings(red_only=True))
        engine.step(sample(1, [[40,40,60,60]]), 0, True)
        self.assertTrue(engine.step(sample(2, [], .01), .01, False)[3])
        self.assertEqual(engine.step(sample(3, [], .16), .16, False)[0], 1)

    def test_three_distinct_misses_and_stale(self):
        engine = Engine(Settings(red_only=True))
        engine.step(sample(1, []), 0)
        miss = sample(2, [], .01, red=False)
        for _ in range(10):
            self.assertTrue(engine.step(miss, .01)[3])
        self.assertTrue(engine.step(sample(3, [], .02, red=False), .02)[3])
        self.assertFalse(engine.step(sample(4, [], .03, red=False), .03)[3])
        engine.step(sample(5, [], .04), .04)
        self.assertEqual(engine.step(sample(5, [], .04), .25), (0,0,0,False))

    def test_movement_requires_right_and_new_yolo_result(self):
        engine = Engine(Settings(red_only=True, move=True))
        result = sample(1, [[70,70,90,90]])
        result['boxes_key'] = (1, 1, 1)
        self.assertEqual(engine.step(result, 0, False)[1:3], (0,0))
        self.assertNotEqual(engine.step(result, .01, True)[1:3], (0,0))
        newer = sample(2, [[70,70,90,90]], .02)
        newer['boxes_key'] = (1, 1, 1)
        self.assertEqual(engine.step(newer, .02, True)[1:3], (0,0))

    def test_default_still_requires_right_and_target(self):
        self.assertEqual(Engine(Settings()).step(sample(1, []), 0, True), (0,0,0,False))
        self.assertEqual(Engine(Settings()).step(sample(1, [[40,40,60,60]]), 0, False), (0,0,0,False))

    def test_red_loop_does_not_wait_for_detector(self):
        app = App.__new__(App)
        app.frames, app.red_results = Latest(), Latest()
        app.shutdown, app.lock = threading.Event(), threading.Lock()
        app.active, app.epoch, app.red_settings = True, 1, RedSettings()
        errors = []
        app.emit = errors.append
        app.stop = lambda: app.shutdown.set()
        rgb = np.zeros((640,640,3),np.uint8)
        rgb[380:384,280:300] = (255,0,0)
        app.frames.put(Frame(1,rgb,time.monotonic(),1))
        worker = threading.Thread(target=app.red_loop)
        worker.start()
        try:
            deadline = time.monotonic() + 1
            while app.red_results.get() is None and time.monotonic() < deadline:
                time.sleep(.002)
            self.assertFalse(errors)
            self.assertTrue(app.red_results.get()['red']['hit'])
        finally:
            app.shutdown.set()
            worker.join(1)

    def test_worker_shift_release_sends_button_up(self):
        shift = [False]
        events = []
        with patch.object(Output, 'emergency_key', return_value=False), \
             patch.object(Output, 'shift_key', side_effect=lambda: shift[0]):
            output = Output(lambda: None, events.append, FakePort,
                            get_red_result=lambda: sample(1, [], time.monotonic()))
            try:
                output.request('connect', 'FAKE')
                deadline = time.monotonic() + 1
                while not output.controller.v4 and time.monotonic() < deadline:
                    time.sleep(.002)
                output.request('arm', Settings(red_only=True, shift_hold=True))
                deadline = time.monotonic() + 1
                while not output.armed and time.monotonic() < deadline:
                    time.sleep(.002)
                self.assertTrue(output.armed)
                self.assertFalse(output.controller.injected)
                shift[0] = True
                deadline = time.monotonic() + 1
                while not output.controller.injected and time.monotonic() < deadline:
                    time.sleep(.002)
                self.assertTrue(output.controller.injected)
                shift[0] = False
                deadline = time.monotonic() + 1
                while output.controller.injected and time.monotonic() < deadline:
                    time.sleep(.002)
                self.assertFalse(output.controller.injected)
                reports = [f[5:] for f in output.controller.port.writes
                           if f[:2] == b'\xde\xad' and f[4] == 0x11]
                self.assertEqual(reports[0], b'\x01')
                self.assertEqual(reports[-1], b'\x00')
            finally:
                output.close()
                output.thread.join(1)

    def test_worker_red_only_without_right_releases_on_stop(self):
        class NoRightPort(FakePort):
            def write(self, data):
                result = super().write(data)
                if data[:2] == b'\xde\xad' and data[4] == 0x55:
                    self.rx = self.rx[:-1] + b'\x00'
                return result
        events = []
        with patch.object(Output, 'emergency_key', return_value=False):
            output = Output(lambda: None, events.append, NoRightPort,
                            get_red_result=lambda: sample(1, [], time.monotonic()))
            try:
                output.request('connect', 'FAKE')
                deadline = time.monotonic() + 1
                while not output.controller.v4 and time.monotonic() < deadline:
                    time.sleep(.002)
                output.request('arm', Settings(red_only=True))
                deadline = time.monotonic() + 1
                while not output.controller.injected and time.monotonic() < deadline:
                    time.sleep(.002)
                self.assertTrue(output.controller.injected)
                self.assertFalse(output.controller.right(time.monotonic()))
                output.stop()
                deadline = time.monotonic() + 1
                while output.armed and time.monotonic() < deadline:
                    time.sleep(.002)
                reports = [f[5:] for f in output.controller.port.writes
                           if f[:2] == b'\xde\xad' and f[4] == 0x11]
                self.assertEqual(reports[0], b'\x01')
                self.assertEqual(reports[-1], b'\x00')
            finally:
                output.close()
                output.thread.join(1)


if __name__ == '__main__':
    unittest.main()
