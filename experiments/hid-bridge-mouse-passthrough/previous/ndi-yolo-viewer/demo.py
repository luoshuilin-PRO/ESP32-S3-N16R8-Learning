"""离线模拟：两张静态素材交替，阻止网络来源与任何 COM/鼠标输出。"""
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
import numpy as np
from PIL import Image
from main import App
from core import Frame


class Demo(App):
    def __init__(self,root):
        super().__init__(root)
        root.title("离线模拟 · 不连接 NDI/COM，不输出鼠标")
        self.provider.set("CPUExecutionProvider")
        base=Path(__file__).parent
        self.model_path.set(str(base/"models/cf.onnx"))
        self.images=[np.asarray(Image.open(base/"samples"/name).convert("RGB")) for name in (
            "1791869812607756200-frame.png","1791870144176117900-frame.png")]
        self.index=0
        self.tick()
        self.load()
        root.after(100,self.wait_model)

    def wait_model(self):
        if self.closing:
            return
        if self.model_busy:
            self.root.after(100,self.wait_model)
        elif self.detector:
            self.start()
            self.status.set("离线素材交替；CPU 推理，不代表真实串流性能")

    def tick(self):
        if self.closing:
            return
        self.index+=1
        rgb=self.images[(self.index//20)%2]
        self.frames.put(Frame(self.index,rgb,time.monotonic(),0))
        self.recv_fps=10
        self.root.after(100,self.tick)

    def connect(self):
        messagebox.showinfo("离线模拟","真实 NDI 请使用 start-vision.cmd；模拟入口不连接网络。")

    def discover(self):
        self.connect()

    def connect_com(self):
        messagebox.showinfo("离线模拟","模拟入口禁止 COM 和鼠标输出。")

    def arm_output(self):
        self.connect_com()

    def output_result(self):
        return None


if __name__=="__main__":
    root=tk.Tk()
    Demo(root)
    root.mainloop()
