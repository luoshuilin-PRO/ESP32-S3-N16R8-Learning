"""明确确认后只读查询 A 板真实按钮；不订阅、不注入移动或点击。"""
import argparse
import json
import sys
import time
from pathlib import Path
from makcu_transport import Transport


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port",required=True)
    parser.add_argument("--seconds",type=float,default=30)
    args=parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8",errors="replace")
    controller=Transport(print)
    records=[]
    previous=None
    try:
        controller.connect(args.port,115200)
        print("已确认 M 板与 V4。现在按下、松开真实鼠标右键；本工具不发送输入。",flush=True)
        deadline=time.monotonic()+args.seconds
        while time.monotonic()<deadline:
            right=controller.poll_buttons()
            if controller.physical_mask!=previous:
                previous=controller.physical_mask
                item={"time":time.time(),"mask":previous,"right":right}
                records.append(item)
                print(item,flush=True)
            time.sleep(.02)
    finally:
        controller.close()
        (Path(__file__).parent/"buttons-check.json").write_text(json.dumps(records,indent=2),encoding="utf-8")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
