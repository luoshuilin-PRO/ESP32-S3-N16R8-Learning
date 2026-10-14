"""NDI＋ONNX 预览，可选 HID-Bridge 输出；默认关闭，不自动连接串口。"""
import json
import queue
import threading
import time
from dataclasses import asdict
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from core import Latest, fit, selection, crop_rect
from detector import Detector
from ndi_input import scan, receive
from output_control import Output, Settings
from red_detector import detect_red, RedSettings
from serial.tools import list_ports

ROOT = Path(__file__).parent


class App:
    def __init__(self, root):
        """输入 Tk 窗口，创建只读 UI；网络连接和模型加载均由用户发起。"""
        self.root = root
        root.title("NDI YOLO · 识别与 HID-Bridge")
        root.geometry("1120x880")
        root.minsize(1000, 740)
        self.frames, self.results = Latest(), Latest()
        self.events = queue.Queue(maxsize=64)
        self.shutdown, self.recv_stop = threading.Event(), threading.Event()
        self.threads = []
        self.lock = threading.Lock()
        self.detector = None
        self.active = False
        self.epoch = 0
        self.stream = 0
        self.roi = None
        self.roi_size = None
        self.settings = (0.25, set())
        self.display = None
        self.drag = None
        self.closing = False
        self.receive_thread = None
        self.model_busy = False
        self.output = None
        self.output_connected = False
        self.output_armed = False
        self.red_settings = RedSettings()
        self.recv_fps = self.infer_fps = 0.0
        self.status = tk.StringVar(value="未连接")
        self.model_status = tk.StringVar(value="模型未加载")
        self.coords = tk.StringVar(value="区域：全画面")
        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")
        self.source = ttk.Combobox(top, state="readonly", width=45)
        self.source.pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="刷新来源", command=self.discover).pack(side="left", padx=4)
        ttk.Button(top, text="连接", command=self.connect).pack(side="left", padx=4)
        ttk.Button(top, text="断开", command=self.disconnect).pack(side="left")
        model = ttk.Frame(root, padding=(8, 0, 8, 8))
        model.pack(fill="x")
        self.model_path = tk.StringVar(value=str(ROOT / "models" / "cf.onnx"))
        ttk.Entry(model, textvariable=self.model_path).pack(side="left", fill="x", expand=True)
        ttk.Button(model, text="选择模型", command=self.choose_model).pack(side="left", padx=4)
        self.provider = ttk.Combobox(model, state="readonly", width=21, values=("DmlExecutionProvider", "CPUExecutionProvider"))
        self.provider.set("DmlExecutionProvider")
        self.provider.pack(side="left")
        ttk.Button(model, text="加载", command=self.load).pack(side="left", padx=4)
        settings = ttk.Frame(root, padding=(8, 0, 8, 8))
        settings.pack(fill="x")
        self.layout = ttk.Combobox(settings, state="readonly", width=7, values=("v5", "v8", "xyxy"))
        self.layout.set("v5")
        self.layout.pack(side="left")
        ttk.Label(settings, text="类别数").pack(side="left", padx=4)
        self.classes = ttk.Spinbox(settings, from_=1, to=1000, width=5)
        self.classes.set(2)
        self.classes.pack(side="left")
        ttk.Label(settings, text="置信度").pack(side="left", padx=4)
        self.conf = ttk.Spinbox(settings, from_=0.01, to=1, increment=.05, width=6)
        self.conf.set(.25)
        self.conf.pack(side="left")
        ttk.Label(settings, text="类别筛选").pack(side="left", padx=4)
        self.filter = ttk.Entry(settings, width=9)
        self.filter.pack(side="left")
        ttk.Button(settings, text="开始识别", command=self.start).pack(side="left", padx=4)
        ttk.Button(settings, text="停止识别", command=self.stop).pack(side="left")
        ttk.Button(settings, text="静态图片测试", command=self.static).pack(side="left", padx=4)
        ttk.Label(root, textvariable=self.model_status, padding=(8, 0)).pack(anchor="w")
        controls = ttk.Frame(root, padding=8)
        controls.pack(fill="x")
        ttk.Label(controls,text="M 板 COM").pack(side="left")
        self.com = ttk.Combobox(controls,state="readonly",width=9)
        self.com.pack(side="left",padx=4)
        ttk.Button(controls,text="刷新串口",command=self.scan_com).pack(side="left")
        ttk.Button(controls,text="连接／查询",command=self.connect_com).pack(side="left",padx=4)
        ttk.Button(controls,text="断开 COM",command=self.disconnect_com).pack(side="left")
        self.click_enabled = tk.BooleanVar(value=True)
        self.move_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls,text="右键＋红名连点",variable=self.click_enabled,command=self.disarm_output).pack(side="left",padx=8)
        ttk.Checkbutton(controls,text="右键头部跟随",variable=self.move_enabled,command=self.disarm_output).pack(side="left")
        self.arm_button = ttk.Button(controls,text="启用输出",command=self.arm_output,state="disabled")
        self.arm_button.pack(side="left",padx=8)
        ttk.Button(controls,text="停止输出",command=self.disarm_output).pack(side="left")
        timing = ttk.Frame(root,padding=(8,0,8,8))
        timing.pack(fill="x")
        self.output_inputs = {}
        for key,label,value,low,high,step in (
            ("press_ms","按下 ms",50,10,500,10),
            ("gap_ms","松开 ms",100,10,1000,10),
            ("stale_ms","旧帧 ms",200,80,500,10),
            ("gain","移动比例",.05,.001,.25,.01),
            ("max_step","步长上限",4,1,10,1),
            ("radius","选择半径",150,10,1000,10)):
            ttk.Label(timing,text=label).pack(side="left",padx=(0,3))
            widget = ttk.Spinbox(timing,from_=low,to=high,increment=step,width=6)
            widget.set(value)
            widget.pack(side="left",padx=(0,8))
            self.output_inputs[key] = widget
        self.output_status = tk.StringVar(value="COM 未连接，输出关闭")
        ttk.Label(root,textvariable=self.output_status,padding=(8,0)).pack(anchor="w")
        self.physical_status = tk.StringVar(value="真实右键：未知")
        ttk.Label(root,textvariable=self.physical_status,padding=(8,0)).pack(anchor="w")
        self.canvas = tk.Canvas(root, background="#141719", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=8, pady=8)
        self.canvas.bind("<ButtonPress-1>", self.drag_start)
        self.canvas.bind("<B1-Motion>", self.drag_move)
        self.canvas.bind("<ButtonRelease-1>", self.drag_end)
        bottom = ttk.Frame(root, padding=8)
        bottom.pack(fill="x")
        ttk.Label(bottom, textvariable=self.coords).pack(side="left", expand=True, fill="x")
        ttk.Button(bottom, text="全画面", command=self.reset_roi).pack(side="left")
        ttk.Button(bottom, text="保存配置", command=self.save_config).pack(side="left", padx=4)
        ttk.Button(bottom, text="读取配置", command=self.read_config).pack(side="left")
        ttk.Button(bottom, text="保存 PNG／结果", command=self.save_sample).pack(side="left", padx=4)
        self.metrics = tk.StringVar()
        ttk.Label(root, textvariable=self.metrics, padding=(8, 0)).pack(anchor="w")
        ttk.Label(root, textvariable=self.status, padding=8).pack(anchor="w")
        self.link = ttk.Label(root, text="NDI® · ndi.video", cursor="hand2", padding=(8, 0))
        self.link.pack(anchor="w")
        self.link.bind("<Button-1>", self.open_ndi)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.spawn(self.infer_loop)
        self.output = Output(self.output_result,self.emit)
        root.bind("<F8>",lambda _:self.disarm_output())
        root.after(40, self.poll)

    def scan_com(self):
        """仅枚举端口，不自动选择或打开。"""
        self.com["values"] = [port.device for port in list_ports.comports()]
        self.com.set("")

    def connect_com(self):
        if self.com.get() and not self.output_armed:
            self.output.request("connect",self.com.get())

    def disconnect_com(self):
        self.disarm_output()
        self.output.request("disconnect")

    def disarm_output(self):
        """UI 紧急停止独立于串口任务队列，恢复需再次确认。"""
        if self.output:
            self.output.stop()
        self.output_armed = False
        self.output_status.set("输出关闭；若曾注入按钮，正在发送释放")

    def arm_output(self):
        """明确确认后启用输出；参数冻结，任意识别配置变化自动撤销许可。"""
        if self.output_armed:
            return
        try:
            values = {key:float(widget.get()) if key == "gain" else int(widget.get())
                      for key,widget in self.output_inputs.items()}
            cfg = Settings(click=self.click_enabled.get(),move=self.move_enabled.get(),**values)
            cfg.validate()
            with self.lock:
                if not self.active:
                    raise ValueError("先开始识别")
            if not self.output_connected or not (cfg.click or cfg.move):
                raise ValueError("先连接并确认 M 板，选择至少一种输出")
            if messagebox.askyesno("确认主机输入",f"按住真实右键时通过 A 板控制主机。\n红名连点：{cfg.click}\n头部跟随：{cfg.move}\n按下 {cfg.press_ms}ms／松开 {cfg.gap_ms}ms\n\n先松开物理左右键，确认主机当前窗口可接受输入。现在启用？"):
                self.output.halt.clear()
                self.output.request("arm",cfg)
        except ValueError as error:
            messagebox.showerror("输出参数",str(error))

    def output_result(self):
        """仅提供当前识别会话同来源的结果；断流／配置变化时立即返回 None。"""
        result,frame = self.results.get(),self.frames.get()
        with self.lock:
            active,epoch = self.active,self.epoch
        if not active or result is None or frame is None:
            return None
        if result.get("epoch") != epoch or result["frame"].stream != frame.stream:
            return None
        return result

    def open_ndi(self, event):
        import webbrowser
        webbrowser.open("https://ndi.video")

    def emit(self, value):
        """接收后台状态，仅保留受限条数，避免日志队列积压。"""
        try:
            self.events.put_nowait(value)
        except queue.Full:
            pass

    def spawn(self, function):
        thread = threading.Thread(target=function, daemon=False)
        self.threads = [t for t in self.threads if t.is_alive()]
        self.threads.append(thread)
        thread.start()
        return thread

    def discover(self):
        def work():
            try:
                self.emit(("sources", scan()))
            except Exception as error:
                self.emit(f"扫描失败：{error}")
        self.status.set("扫描 NDI 来源…")
        self.spawn(work)

    def connect(self):
        """手动连接选定源，不连接串口；旧接收线程结束前不创建第二条连接。"""
        if self.receive_thread and self.receive_thread.is_alive():
            messagebox.showinfo("连接", "请先断开并等待接收线程结束")
            return
        name = self.source.get()
        if not name:
            return
        self.stream += 1
        stream = self.stream
        self.recv_stop = threading.Event()
        stop = self.recv_stop
        self.results.put(None)
        def work():
            try:
                receive(name, stop, self.frames, self.emit, stream)
            except Exception as error:
                self.frames.put(None)
                self.emit(f"接收失败：{error}")
        self.receive_thread = self.spawn(work)

    def disconnect(self):
        self.recv_stop.set()
        self.stop()
        self.frames.put(None)
        self.results.put(None)
        self.status.set("断开中")

    def choose_model(self):
        path = filedialog.askopenfilename(filetypes=[("ONNX", "*.onnx")])
        if path:
            self.model_path.set(path)

    def load(self):
        """后台加载模型；先停识别并撤销旧会话，失败时不保留旧模型伪装成功。"""
        if self.model_busy:
            return
        self.stop()
        try:
            count = int(self.classes.get())
            if not 1 <= count <= 1000:
                raise ValueError("类别数范围 1～1000")
        except ValueError as error:
            messagebox.showerror("参数", str(error))
            return
        path, provider, layout = self.model_path.get(), self.provider.get(), self.layout.get()
        self.model_busy = True
        with self.lock:
            self.detector = None
        self.model_status.set("正在加载模型…")
        def work():
            try:
                detector = Detector(path, provider, layout, classes=count)
                with self.lock:
                    self.detector = detector
                self.emit(("model", f"{Path(path).name} | {detector.w}×{detector.h} | {layout} | {detector.providers}（不代表每个节点都在 GPU）"))
            except Exception as error:
                self.emit(("model", f"模型加载失败：{error}"))
            finally:
                self.model_busy = False
        self.spawn(work)

    def parameters(self):
        """读取 UI 配置，返回合法置信度及类别集合。"""
        confidence = float(self.conf.get())
        allowed = {int(x.strip()) for x in self.filter.get().split(",") if x.strip()}
        if not .01 <= confidence <= 1 or any(x < 0 for x in allowed):
            raise ValueError("置信度或类别编号非法")
        return confidence, allowed

    def start(self):
        self.disarm_output()
        try:
            settings = self.parameters()
            with self.lock:
                if self.detector is None:
                    raise ValueError("先加载模型")
                if any(x >= self.detector.classes for x in settings[1]):
                    raise ValueError("类别筛选超出模型范围")
                self.settings = settings
                self.active = True
                self.epoch += 1
            self.status.set("只读识别已启用")
        except ValueError as error:
            messagebox.showerror("识别", str(error))

    def stop(self):
        if self.output:
            self.output.stop()
        with self.lock:
            self.active = False
            self.epoch += 1
        self.results.put(None)

    def infer_loop(self):
        """只处理最新且未过期的一帧；结果绑定原帧，禁止旧框叠到新图。"""
        last = None
        count, start = 0, time.monotonic()
        while not self.shutdown.wait(.005):
            frame = self.frames.get()
            with self.lock:
                active, epoch, detector = self.active, self.epoch, self.detector
                roi, roi_size, settings = self.roi, self.roi_size, self.settings
            if not active or frame is None or time.monotonic() - frame.received > 2:
                continue
            key = (frame.stream, frame.sequence, epoch)
            if key == last:
                continue
            last = key
            try:
                h, w = frame.rgb.shape[:2]
                if roi and roi_size != (w, h):
                    raise ValueError("视频分辨率变化，请重新框选区域")
                x, y, rw, rh = crop_rect(roi, w, h)
                queued = (time.monotonic() - frame.received) * 1000
                boxes, infer_ms, total = detector.detect(frame.rgb[y:y + rh, x:x + rw], *settings)
                red_start=time.perf_counter()
                red = detect_red(frame.rgb,self.red_settings)
                total+=(time.perf_counter()-red_start)*1000
                for item in boxes:
                    item["box"] = [v + (x if i % 2 == 0 else y) for i, v in enumerate(item["box"])]
                with self.lock:
                    if self.active and self.epoch == epoch:
                        self.results.put({"frame": frame, "boxes": boxes, "infer_ms": infer_ms,
                                          "processing_ms": total, "queue_ms": queued, "roi": [x,y,rw,rh],"epoch":epoch,"red":red})
                count += 1
                now = time.monotonic()
                if now - start >= 1:
                    self.emit(("infer_fps", count / (now - start)))
                    count, start = 0, now
            except Exception as error:
                self.stop()
                self.emit(f"识别停止：{error}")

    def static(self):
        """用户选一张图片，后台识别并保存标注预览及 JSON；不更改实时输入。"""
        path = filedialog.askopenfilename(filetypes=[("图片", "*.png *.bmp *.jpg *.jpeg")])
        with self.lock:
            detector = self.detector
        if not path or detector is None:
            return
        try:
            settings = self.parameters()
        except ValueError as error:
            messagebox.showerror("参数", str(error))
            return
        self.stop()
        def work():
            try:
                import numpy as np
                rgb = np.asarray(Image.open(path).convert("RGB"))
                boxes, ms, total = detector.detect(rgb, *settings)
                directory = ROOT / "samples"
                directory.mkdir(exist_ok=True)
                stamp = str(time.time_ns())
                from PIL import ImageDraw
                image = Image.fromarray(rgb)
                draw = ImageDraw.Draw(image)
                for box in boxes:
                    draw.rectangle(box["box"], outline="lime", width=2)
                    draw.text(box["box"][:2], f"{box['class']} {box['score']:.2f}", fill="yellow")
                image.save(directory / f"static-{stamp}.png")
                (directory / f"static-{stamp}.json").write_text(json.dumps({"boxes": boxes,"infer_ms":ms,"processing_ms":total}, indent=2), encoding="utf-8")
                self.emit(f"静态测试完成：{len(boxes)} 个框，推理 {ms:.2f}ms，已保存 samples")
            except Exception as error:
                self.emit(f"静态测试失败：{error}")
        self.spawn(work)

    def drag_start(self, event):
        if self.display:
            self.drag = (event.x, event.y)

    def drag_move(self, event):
        self.canvas.delete("drag")
        if self.drag:
            self.canvas.create_rectangle(*self.drag, event.x, event.y, outline="#ffdc4a", tags="drag")

    def drag_end(self, event):
        self.canvas.delete("drag")
        if self.drag and self.display:
            h, w = self.display[0].shape[:2]
            roi = selection(self.drag, (event.x, event.y), (w,h), (self.canvas.winfo_width(),self.canvas.winfo_height()))
            if roi:
                self.disarm_output()
                with self.lock:
                    self.roi, self.roi_size = roi, (w,h)
                    self.epoch += 1
                self.results.put(None)
                self.coords.set(f"区域 x={roi[0]} y={roi[1]} w={roi[2]} h={roi[3]} | 原图 {w}×{h}")
        self.drag = None

    def reset_roi(self):
        self.disarm_output()
        with self.lock:
            self.roi = self.roi_size = None
            self.epoch += 1
        self.results.put(None)
        self.coords.set("区域：全画面")

    def save_config(self):
        try:
            confidence, allowed = self.parameters()
            data = {"model": self.model_path.get(), "provider":self.provider.get(), "layout":self.layout.get(),
                    "classes":int(self.classes.get()), "confidence":confidence, "allowed":sorted(allowed),
                    "roi":self.roi, "roi_size":self.roi_size, "source":self.source.get(),"red":asdict(self.red_settings)}
            (ROOT / "config.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.status.set("配置已保存")
        except Exception as error:
            messagebox.showerror("配置", str(error))

    def read_config(self):
        try:
            data = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
            self.stop()
            red_data=data.get("red",{})
            if "roi" in red_data:
                red_data["roi"]=tuple(red_data["roi"])
            if "size" in red_data:
                red_data["size"]=tuple(red_data["size"])
            red=RedSettings(**red_data)
            red.validate()
            self.red_settings=red
            with self.lock:
                self.detector = None
                self.roi = tuple(data["roi"]) if data.get("roi") else None
                self.roi_size = tuple(data["roi_size"]) if data.get("roi_size") else None
            self.model_path.set(data["model"])
            self.provider.set(data["provider"])
            self.layout.set(data["layout"])
            self.classes.set(data["classes"])
            self.conf.set(data["confidence"])
            self.filter.delete(0,"end")
            self.filter.insert(0, ",".join(map(str,data["allowed"])))
            self.source.set(data["source"])
            self.coords.set(f"区域：{self.roi or '全画面'}")
            self.model_status.set("配置已读取，请重新加载模型")
        except Exception as error:
            messagebox.showerror("配置", str(error))

    def save_sample(self):
        """保存当前显示对应的原始帧、ROI PNG 和同帧结果，不录制视频。"""
        if self.display is None:
            return
        try:
            rgb, result = self.display
            h, w = rgb.shape[:2]
            x,y,rw,rh = crop_rect(self.roi,w,h)
            directory = ROOT / "samples"
            directory.mkdir(exist_ok=True)
            stamp = str(time.time_ns())
            Image.fromarray(rgb).save(directory / f"{stamp}-frame.png")
            Image.fromarray(rgb[y:y+rh,x:x+rw]).save(directory / f"{stamp}-roi.png")
            details = {k:v for k,v in (result or {}).items() if k != "frame"}
            details.update({"roi":[x,y,rw,rh],"original_size":[w,h]})
            (directory / f"{stamp}.json").write_text(json.dumps(details,indent=2),encoding="utf-8")
            self.status.set("样本已保存")
        except Exception as error:
            messagebox.showerror("保存",str(error))

    def poll(self):
        while not self.events.empty():
            event = self.events.get()
            if isinstance(event, str):
                self.status.set(event)
            elif event[0] == "sources":
                self.source["values"] = event[1]
                self.status.set(f"发现 {len(event[1])} 个 NDI 来源，请手动选择")
            elif event[0] == "model":
                self.model_status.set(event[1])
            elif event[0] == "fps":
                self.recv_fps = event[1]
            elif event[0] == "infer_fps":
                self.infer_fps = event[1]
            elif event[0] == "output_connected":
                self.output_connected = event[1]
                self.arm_button["state"] = "normal" if event[1] else "disabled"
                self.output_status.set("M 板已确认，输出关闭" if event[1] else "COM 未连接，输出关闭")
                if not event[1]:
                    self.physical_status.set("真实右键：未知／连接失效")
            elif event[0] == "output_armed":
                self.output_armed = event[1]
                self.arm_button["state"] = "normal" if self.output_connected and not event[1] else "disabled"
                self.output_status.set("输出已启用" if event[1] else "输出关闭")
            elif event[0] == "physical":
                self.physical_status.set(f"真实右键：{'按下' if event[1]&2 else '松开'} | 物理掩码 {event[1]}")
        frame = self.frames.get()
        result = self.results.get()
        if result and (frame is None or result["frame"].stream != frame.stream or time.monotonic() - result["frame"].received > 2):
            result = None
        shown = result["frame"] if result else frame
        self.canvas.delete("image", "box", "roi")
        self.display = None
        if shown and time.monotonic() - shown.received <= 2:
            rgb = shown.rgb
            h,w = rgb.shape[:2]
            dw,dh,ox,oy = fit(w,h,max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height()))
            self.photo = ImageTk.PhotoImage(Image.fromarray(rgb).resize((dw,dh)))
            self.canvas.create_image(ox,oy,anchor="nw",image=self.photo,tags="image")
            self.canvas.tag_lower("image")
            self.canvas.create_line(ox+dw/2-8,oy+dh/2,ox+dw/2+8,oy+dh/2,fill="#ffffff",tags="box")
            self.canvas.create_line(ox+dw/2,oy+dh/2-8,ox+dw/2,oy+dh/2+8,fill="#ffffff",tags="box")
            for item in result["boxes"] if result else []:
                x1,y1,x2,y2 = item["box"]
                coords = (ox+x1*dw/w,oy+y1*dh/h,ox+x2*dw/w,oy+y2*dh/h)
                self.canvas.create_rectangle(*coords,outline="#35df9a",width=2,tags="box")
                self.canvas.create_text(coords[0],max(oy,coords[1]-12),anchor="nw",text=f"{item['class']} {item['score']:.2f}",fill="#35df9a",tags="box")
            if self.roi and self.roi_size == (w,h):
                x,y,rw,rh = self.roi
                self.canvas.create_rectangle(ox+x*dw/w,oy+y*dh/h,ox+(x+rw)*dw/w,oy+(y+rh)*dh/h,outline="#ffdc4a",tags="roi")
            if (w,h)==self.red_settings.size:
                x,y,rw,rh=self.red_settings.roi
                self.canvas.create_rectangle(ox+x*dw/w,oy+y*dh/h,ox+(x+rw)*dw/w,oy+(y+rh)*dh/h,outline="#ee705a",tags="roi")
            self.display = (rgb,result)
        metrics = f"接收 {self.recv_fps:.1f} FPS | 推理 {self.infer_fps if self.active else 0:.1f} FPS"
        if result:
            metrics += f" | 推理 {result['infer_ms']:.1f}ms | 处理 {result['processing_ms']:.1f}ms | 本地排队 {result['queue_ms']:.1f}ms"
            red=result.get("red",{})
            metrics += f" | 红名 {'命中' if red.get('hit') else '未命中'} ({red.get('pixels',0)})"
        self.metrics.set(metrics)
        if self.closing and not any(t.is_alive() for t in self.threads) and not self.output.thread.is_alive():
            self.root.destroy()
            return
        self.root.after(40,self.poll)

    def close(self):
        self.closing = True
        self.shutdown.set()
        self.output.close()
        self.disconnect()
        self.status.set("正在等待接收和推理线程退出…")


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
