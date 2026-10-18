"""在已有静态样本上核对推理与 UI，生成自身窗口截图，不接网络或串口。"""
import json
import time
import statistics
import numpy as np
import tkinter as tk
from PIL import Image, ImageDraw, ImageGrab
from pathlib import Path
from detector import Detector
from core import Frame
from main import App

ROOT = Path(__file__).parent
path = ROOT / "samples/1791869812607756200-frame.png"
rgb = np.array(Image.open(path).convert("RGB"))
detector = Detector(str(ROOT / "models/cf.onnx"),"DmlExecutionProvider","v5",classes=2)
results = [detector.detect(rgb,.25,set()) for _ in range(10)]
boxes, ms, total = results[-1]
image = Image.fromarray(rgb)
draw = ImageDraw.Draw(image)
for item in boxes:
    draw.rectangle(item["box"],outline="lime",width=3)
image.save(ROOT / "samples/static-annotated.png")
report = {"sample":path.name,"size":list(image.size),"boxes":boxes,"providers":detector.providers,
          "infer_median_ms":statistics.median(r[1] for r in results),"semantic_accuracy_verified":False}
(ROOT / "static-check.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
root = tk.Tk()
app = App(root)
app.detector = detector
app.model_status.set("cf.onnx | v5 | DmlExecutionProvider, CPUExecutionProvider")
app.frames.put(Frame(1,rgb,time.monotonic(),1))
app.results.put({"frame":app.frames.get(),"boxes":boxes,"infer_ms":ms,"processing_ms":total,"queue_ms":0,"roi":[0,0,rgb.shape[1],rgb.shape[0]]})
def capture():
    try:
        root.update()
        ImageGrab.grab(bbox=(root.winfo_rootx(),root.winfo_rooty(),root.winfo_rootx()+root.winfo_width(),root.winfo_rooty()+root.winfo_height())).save(ROOT / "ui-check.png")
    finally:
        app.close()
root.after(500,capture)
root.mainloop()
print(report)
