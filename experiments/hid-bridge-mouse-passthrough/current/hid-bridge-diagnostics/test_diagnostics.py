"""模拟端口、UDP 与报告边界，不接触真实设备。"""
import copy
import threading
import unittest
from unittest.mock import patch
from protocol import encode,Scanner,crc16
from makcu_transport import V4Scanner
from checks import diagnose,compare,kmbox,active_test,set_device_baud


class FakePort:
    instances=[]
    role=2
    def __init__(self,**kwargs):
        self.is_open=False
        self.rx=b""
        self.writes=[]
        self.dtr=self.rts=True
        self.baudrate=kwargs["baudrate"]
        FakePort.instances.append(self)
    def open(self):
        assert not self.dtr and not self.rts
        self.is_open=True
    def close(self):
        self.is_open=False
    @property
    def in_waiting(self):
        return len(self.rx)
    def write(self,data):
        self.writes.append(data)
        if data[:2]==b"\xa5\x5a" and data[3]==6:
            self.rx+=encode(7,int.from_bytes(data[4:6],"little"),b"HIDBRDG2"+data[7:-2]+bytes([self.role]))
        elif data[:2]==b"\xde\xad":
            op=data[4]
            payload={2:b"\x01",4:(4).to_bytes(4,"little"),0x55:b"\x00",0x56:bytes(40),
                     0x1F:b"\x00",0x64:b"\x80\x07\x38\x04",0x66:b"\x00",0xA4:self.baudrate.to_bytes(4,"little")}.get(op)
            if payload is not None:
                self.rx+=b"\xde\xad"+len(payload).to_bytes(2,"little")+bytes([op])+payload
        return len(data)
    def read(self,count):
        data,self.rx=self.rx[:count],self.rx[count:]
        return data


class Tests(unittest.TestCase):
    def setUp(self):
        FakePort.instances=[]
        FakePort.role=2
        self.config={"query_timeout_seconds":.2,"snapshot_gap_seconds":.01}
        self.first={"roleId":2,"uptimeMilliseconds":1000,"counters":{"uart1_rx":10,"uart1_tx":10,"errors":0},"queues":[],"state":{}}
        self.second=copy.deepcopy(self.first)
        self.second["uptimeMilliseconds"]=1010
        self.second["counters"].update(uart1_rx=11,uart1_tx=11)

    def test_crc_vector(self):
        self.assertEqual(crc16(b"123456789"),0x29B1)

    def test_a5_fragment(self):
        f=encode(7,12,b"a")
        s=Scanner()
        self.assertEqual(s.feed(f[:1]),[])
        self.assertEqual(s.feed(f[1:]),[(7,12,b"a")])

    def test_v4_fragment(self):
        s=V4Scanner()
        self.assertEqual(s.feed(b"abc\xde"),[])
        self.assertEqual(s.feed(b"\xad\x01\x00\x55\x02"),[(0x55,b"\x02")])

    def test_statistics_continuity(self):
        continuity,activity,diff=compare(self.first,self.second,.01)
        self.assertTrue(continuity and activity)
        self.assertEqual(diff["uart1_rx"],1)

    def test_reset_detected(self):
        self.second["uptimeMilliseconds"]=1
        self.assertFalse(compare(self.first,self.second,.01)[0])

    def test_idle_not_fake_failure(self):
        self.second["counters"]=self.first["counters"]
        self.assertFalse(compare(self.first,self.second,.01)[1])

    def test_diagnosis_no_input(self):
        with patch("controller.serial.Serial",FakePort), patch("checks.snapshot",side_effect=[self.first,self.second]):
            r=diagnose("FAKE",115200,self.config,lambda _:None,threading.Event())
        checks={i["name"]:i for i in r["checks"]}
        self.assertEqual(checks["固件协议／角色"]["status"],"通过")
        self.assertEqual(checks["Makcu 设备波特率"]["status"],"通过")
        self.assertEqual(checks["主机实际鼠标透传"]["status"],"未验证")
        for p in FakePort.instances:
            self.assertFalse(p.is_open)
            for f in p.writes:
                if f[:2]==b"\xde\xad":
                    self.assertNotIn(f[4],(0x18,0x61,0xA5))
                    self.assertFalse(f[4]==0x11 and len(f)>5)
                else:
                    self.assertNotIn(f[3],(2,3,5))

    def test_isolated_role_not_failed(self):
        FakePort.role=0
        with patch("controller.serial.Serial",FakePort):
            r=diagnose("FAKE",921600,self.config,lambda _:None,threading.Event())
        self.assertTrue(any(i["status"]=="不适用" for i in r["checks"]))
        self.assertFalse(any(i["status"]=="失败" for i in r["checks"]))

    def test_active_release(self):
        with patch("controller.serial.Serial",FakePort):
            r=active_test("FAKE",115200,"click",threading.Event(),lambda _:None)
        reports=[f[5:] for f in FakePort.instances[-1].writes if f[:2]==b"\xde\xad" and f[4]==0x11]
        self.assertEqual(reports,[b"\x01",b"\x00"])
        self.assertEqual(r["checks"][1]["status"],"未验证")

    def test_baud_allowed(self):
        with self.assertRaises(ValueError):
            set_device_baud("FAKE",115200,921600,lambda _:None)

    def test_baud_set_simulated(self):
        with patch("controller.serial.Serial",FakePort):
            r=set_device_baud("FAKE",115200,115200,lambda _:None)
        self.assertEqual(r["checks"][0]["status"],"通过")

    def test_udp_echo(self):
        class Socket:
            def __init__(self,*args):
                pass
            def __enter__(self):
                return self
            def __exit__(self,*args):
                pass
            def settimeout(self,t):
                pass
            def sendto(self,data,address):
                self.packet,self.address=data,address
            def recvfrom(self,size):
                return self.packet,self.address
        with patch("checks.socket.socket",Socket):
            r=kmbox("127.0.0.1",24814,"AF425414")
        self.assertEqual(r["checks"][0]["status"],"通过")

    def test_udp_bad_params(self):
        with self.assertRaises(ValueError):
            kmbox("127.0.0.1",70000,"AF425414")

    def test_cancel_before_input(self):
        stop=threading.Event()
        stop.set()
        with patch("controller.serial.Serial",FakePort):
            with self.assertRaises(InterruptedError):
                active_test("FAKE",115200,"click",stop,lambda _:None)
        self.assertEqual(FakePort.instances,[])

    def test_cancel_before_diagnosis(self):
        stop=threading.Event()
        stop.set()
        with patch("controller.serial.Serial",FakePort):
            result=diagnose("FAKE",115200,self.config,lambda _:None,stop)
        self.assertEqual(FakePort.instances,[])
        self.assertEqual(result["checks"][0]["status"],"失败")

    def test_error_report(self):
        with patch("checks.Controller.connect",side_effect=OSError("端口占用")):
            r=diagnose("FAKE",115200,self.config,lambda _:None,threading.Event())
        self.assertEqual(r["checks"][-1]["status"],"失败")
        self.assertIn("端口占用",r["checks"][-1]["detail"])

    def test_uuid_length(self):
        with self.assertRaises(ValueError):
            kmbox("127.0.0.1",24814,"1")


if __name__=="__main__":
    unittest.main()
