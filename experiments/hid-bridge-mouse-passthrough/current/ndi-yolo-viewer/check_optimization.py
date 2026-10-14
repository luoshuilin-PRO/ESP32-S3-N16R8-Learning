"""离线模型计时；不采集屏幕或导入串口输出模块。"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from detector import Detector


def main():
    root=Path(__file__).parent
    detector=Detector(str(root/"models/cf.onnx"),"DmlExecutionProvider","auto",classes=2)
    image=np.asarray(Image.open(root/"samples/1791869812607756200-frame.png").convert("RGB"))
    times=[]
    for _ in range(25):
        boxes,infer,total=detector.detect(image,.25,set())
        times.append((infer,total))
    report={"providers":detector.providers,"layout":detector.layout,
            "static_infer_p50_p95_ms":np.percentile(np.asarray(times)[5:,0],[50,95]).tolist(),
            "static_processing_p50_p95_ms":np.percentile(np.asarray(times)[5:,1],[50,95]).tolist(),
            "boxes":len(boxes),"no_com_or_hid":True}
    (root/"optimization-check.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
