"""VC1 bench test. Abort unless B reports native USB disconnected."""
import argparse
import time
from serial_link import Link, packet


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',default='COM4')
    args=parser.parse_args()
    link=Link(args.port)
    try:
        assert not link.exchange(0), 'Disconnect native USB before this bench test'
        print('PASS HELLO/STOP ACK; native USB disconnected',flush=True)
        for _ in range(20):
            assert not link.exchange(1)
            time.sleep(0.04)
        print('PASS 20 fresh-frame messages acknowledged without HID',flush=True)
        link.exchange(0)
        time.sleep(0.25)
        try:
            link.exchange(1,timeout=0.08)
            raise AssertionError('Expired session accepted ACTIVE')
        except TimeoutError:pass
        print('PASS expired session rejects ACTIVE',flush=True)
        link.exchange(2)
        p=bytearray(packet((link.seq+1)&0xffffffff,1)); p[-1]^=1
        link.port.write(p)
        response=link.port.read(128)
        assert b'VC1 ACK' not in response, response
        link.exchange(0)
        print('PASS bad CRC rejected; STOP still works',flush=True)
    finally:
        link.close()


if __name__=='__main__':main()
