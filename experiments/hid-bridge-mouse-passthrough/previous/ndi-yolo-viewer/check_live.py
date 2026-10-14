"""用户明确同意后使用：短时只读 NDI 接收＋推理，不含串口或输入输出。"""
import argparse
import json
import threading
import time
from pathlib import Path
import statistics
import sys
from PIL import Image, ImageDraw
from core import Latest
from detector import Detector
from ndi_input import receive

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--seconds", type=float, default=10)
    args = parser.parse_args()
    root = Path(__file__).parent
    detector = Detector(str(root / "models/cf.onnx"), "DmlExecutionProvider", "v5", classes=2)
    latest, stop = Latest(), threading.Event()
    errors = []
    def worker():
        try:
            receive(args.source, stop, latest, print, 1)
        except Exception as error:
            errors.append(str(error))
    thread = threading.Thread(target=worker)
    thread.start()
    last = None
    times = []
    saved = False
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline and thread.is_alive():
            frame = latest.get()
            if frame is None or frame.sequence == last:
                time.sleep(.01)
                continue
            last = frame.sequence
            boxes, ms, total = detector.detect(frame.rgb,.25,set())
            times.append(ms)
            if not saved:
                directory = root / "samples"
                directory.mkdir(exist_ok=True)
                image = Image.fromarray(frame.rgb)
                image.save(directory / "live-original.png")
                draw = ImageDraw.Draw(image)
                for box in boxes:
                    draw.rectangle(box["box"],outline="lime",width=2)
                image.save(directory / "live-annotated.png")
                (directory / "live-result.json").write_text(json.dumps({"size":list(image.size),"boxes":boxes,"infer_ms":ms,"processing_ms":total},indent=2),encoding="utf-8")
                saved = True
    finally:
        stop.set()
        thread.join(timeout=10)
    report = {"source":args.source,"providers":detector.providers,"processed_frames":len(times),
              "infer_median_ms":statistics.median(times) if times else None,"errors":errors,
              "receiver_stopped":not thread.is_alive(),"no_com_or_hid":True}
    (root / "live-check.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(report)
    return 0 if times and not errors and not thread.is_alive() else 1


if __name__ == "__main__":
    raise SystemExit(main())
