"""输出逻辑回归；仅使用模拟串口，不连接 COM 或注入系统输入。"""
import threading
import time
import unittest
from unittest.mock import patch
import numpy as np
from core import Frame
from output_control import Engine as BaseEngine, Settings, Output
from protocol import encode


class Engine(BaseEngine):
    def step(self,result,now,right=True):
        return super().step(result,now,right)


def sample(sequence, boxes, received=0, stream=1,red=True):
    return {"frame":Frame(sequence,np.zeros((100,100,3),np.uint8),received,stream),
            "boxes":[{"box":box,"class":1,"score":.9} for box in boxes],"epoch":1,"red":{"hit":red}}


class FakePort:
    instances = []
    def __init__(self,**kwargs):
        self.is_open = False
        self.rx = b""
        self.writes = []
        self.dtr = self.rts = True
        FakePort.instances.append(self)
    def open(self):
        assert not self.dtr and not self.rts
        self.is_open = True
    def close(self):
        self.is_open = False
    @property
    def in_waiting(self):
        return len(self.rx)
    def write(self,data):
        self.writes.append(data)
        if data[:2]==b"\xde\xad":
            opcode=data[4]
            payload={4:(4).to_bytes(4,"little"),0x55:b"\x02"}.get(opcode)
            if payload is not None:
                self.rx+=b"\xde\xad"+len(payload).to_bytes(2,"little")+bytes([opcode])+payload
        elif data[3] == 6:
            self.rx += encode(7,int.from_bytes(data[4:6],"little"),b"HIDBRDG2"+data[7:-2]+b"\x02")
        return len(data)
    def read(self,count):
        result,self.rx = self.rx[:count],self.rx[count:]
        return result


class Tests(unittest.TestCase):
    def test_center_only(self):
        e=Engine(Settings(radius=10))
        self.assertEqual(e.step(sample(1,[[0,0,20,20]]),0),(0,0,0,False))
        self.assertEqual(e.step(sample(2,[[40,40,60,60]]),.01),(1,0,0,True))

    def test_click_period(self):
        e=Engine(Settings())
        s=sample(1,[[40,40,60,60]])
        self.assertEqual(e.step(s,0)[0],1)
        self.assertEqual(e.step(s,.06)[0],0)
        self.assertEqual(e.step(s,.16)[0],1)

    def test_three_misses(self):
        e=Engine(Settings())
        e.step(sample(1,[[40,40,60,60]]),0)
        self.assertTrue(e.step(sample(2,[[40,40,60,60]],.01,red=False),.01)[3])
        self.assertTrue(e.step(sample(3,[[40,40,60,60]],.02,red=False),.02)[3])
        self.assertFalse(e.step(sample(4,[[40,40,60,60]],.03,red=False),.03)[3])

    def test_repeat_is_not_miss(self):
        e=Engine(Settings())
        e.step(sample(1,[[40,40,60,60]]),0)
        miss=sample(2,[[40,40,60,60]],.01,red=False)
        for _ in range(100):
            self.assertTrue(e.step(miss,.01)[3])
        self.assertEqual(e.misses,1)

    def test_stale_releases(self):
        e=Engine(Settings())
        s=sample(1,[[40,40,60,60]])
        e.step(s,0)
        self.assertEqual(e.step(s,.201),(0,0,0,False))

    def test_none_releases(self):
        e=Engine(Settings())
        e.step(sample(1,[[40,40,60,60]]),0)
        self.assertEqual(e.step(None,.01),(0,0,0,False))

    def test_movement_default_off(self):
        self.assertEqual(Engine(Settings()).step(sample(1,[[70,70,90,90]],red=False),0),(0,0,0,False))

    def test_movement_once_per_frame(self):
        e=Engine(Settings(click=False,move=True))
        s=sample(1,[[70,70,90,90]])
        self.assertEqual(e.step(s,0),(0,2,2,True))
        self.assertEqual(e.step(s,.01),(0,0,0,True))

    def test_movement_clamp(self):
        e=Engine(Settings(click=False,move=True,gain=.25,max_step=4))
        self.assertEqual(e.step(sample(1,[[80,80,100,100]]),0)[1:3],(4,4))

    def test_movement_deadzone(self):
        e=Engine(Settings(click=False,move=True))
        self.assertEqual(e.step(sample(1,[[49,49,53,53]]),0)[1:3],(0,0))

    def test_radius(self):
        e=Engine(Settings(click=False,move=True,radius=10))
        self.assertFalse(e.step(sample(1,[[70,70,90,90]]),0)[3])

    def test_nearest(self):
        e=Engine(Settings(click=False,move=True,gain=.1))
        self.assertEqual(e.step(sample(1,[[70,70,90,90],[20,40,40,60]]),0)[1:3],(-2,0))

    def test_parameter_bounds(self):
        with self.assertRaises(ValueError):
            Engine(Settings(press_ms=0))

    def test_no_auto_connect(self):
        FakePort.instances=[]
        o=Output(lambda:None,lambda _:None,FakePort)
        try:
            time.sleep(.03)
            self.assertEqual(FakePort.instances,[])
        finally:
            o.close()
            o.thread.join(2)
        self.assertFalse(o.thread.is_alive())

    def test_worker_click_stop_release(self):
        events=[]
        holder=[sample(1,[[40,40,60,60]],time.monotonic())]
        with patch.object(Output,"emergency_key",return_value=False):
            o=Output(lambda:holder[0],events.append,FakePort)
            try:
                o.request("connect","FAKE")
                deadline=time.monotonic()+1
                while ("output_connected",True) not in events and time.monotonic()<deadline:
                    time.sleep(.005)
                self.assertIn(("output_connected",True),events)
                o.request("arm",Settings())
                deadline=time.monotonic()+1
                while not o.controller.injected and time.monotonic()<deadline:
                    time.sleep(.005)
                self.assertTrue(o.controller.injected)
                o.stop()
                time.sleep(.03)
                reports=[f[5:] for f in o.controller.port.writes if f[:2]==b"\xde\xad" and f[4]==0x11]
                self.assertEqual(reports[0][0],1)
                self.assertEqual(reports[-1][0],0)
                self.assertFalse(o.armed)
            finally:
                o.close()
                o.thread.join(2)
            self.assertFalse(o.thread.is_alive())

    def test_right_release_immediate(self):
        e=Engine(Settings())
        s=sample(1,[[40,40,60,60]])
        self.assertEqual(e.step(s,0)[0],1)
        self.assertEqual(e.step(s,.01,right=False),(0,0,0,False))

    def test_body_only_no_fallback(self):
        s=sample(1,[[40,40,60,60]])
        s["boxes"][0]["class"]=0
        self.assertEqual(Engine(Settings(move=True)).step(s,0),(0,0,0,False))

    def test_head_lost_immediate(self):
        e=Engine(Settings())
        e.step(sample(1,[[40,40,60,60]]),0)
        self.assertEqual(e.step(sample(2,[],.01),.01),(0,0,0,False))

    def test_red_needed(self):
        self.assertEqual(Engine(Settings()).step(sample(1,[[40,40,60,60]],red=False),0),(0,0,0,False))


if __name__=="__main__":
    unittest.main()
