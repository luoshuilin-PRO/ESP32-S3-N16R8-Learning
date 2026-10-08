"""Manual-armed, fixed-monitor ROI preview and B-board vision controller."""
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageGrab, ImageTk
from serial.tools import list_ports
from detector import DEFAULTS, detect, Confirmation
from serial_link import Link
from timing import FrameRate, validate_timing

BASE = Path(__file__).resolve().parent


def monitor_rectangles():
    """Read physical monitor rectangles after process DPI awareness is set."""
    items = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE, wintypes.HDC,
                                      ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    @callback_type
    def callback(handle, dc, rect, data):
        r = rect.contents
        items.append((r.left, r.top, r.right, r.bottom))
        return True
    ctypes.windll.user32.EnumDisplayMonitors(None, None, callback, 0)
    return items


class App:
    def __init__(self, root):
        self.root = root
        root.title('红名像素检测 · B 板控制')
        root.geometry('940x620')
        root.minsize(880, 600)
        self.config = {**DEFAULTS, **json.loads((BASE/'config.json').read_text(encoding='utf-8'))}
        self.monitors = monitor_rectangles()
        self.events = queue.Queue(maxsize=2)
        self.stop = threading.Event()
        self.armed = threading.Event()
        self.worker = None
        self.alive = time.monotonic()
        self.arm_generation = 0
        self.status = tk.StringVar(value='未启动')
        self.stats = tk.StringVar(value='像素：—   状态：—   目标：—   实际：—')
        self.costs = tk.StringVar(value='采集＋识别：—   串口往返：—')
        top = ttk.Frame(root, padding=12)
        top.pack(fill='x')
        self.monitor = ttk.Combobox(top, state='readonly', width=28,
            values=[f'{i+1}: {r[2]-r[0]}×{r[3]-r[1]} ({r[0]},{r[1]})' for i,r in enumerate(self.monitors)])
        self.monitor.current(min(self.config.get('monitor',0), len(self.monitors)-1))
        self.monitor.pack(side='left')
        self.port = ttk.Combobox(top, width=14, values=[p.device for p in list_ports.comports()])
        self.port.set(self.config['port'])
        self.port.pack(side='left', padx=8)
        self.connect = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text='连接 B 板', variable=self.connect).pack(side='left')
        ttk.Button(top, text='刷新串口', command=lambda: self.port.configure(values=[p.device for p in list_ports.comports()])).pack(side='right')
        roi = ttk.Frame(root, padding=(12,0,12,8)); roi.pack(fill='x')
        self.fields = {}
        for key in ('x','y','width','height'):
            ttk.Label(roi,text=key).pack(side='left',padx=4)
            var = tk.StringVar(value=str(self.config['roi'][key])); self.fields[key] = var
            ttk.Entry(roi,textvariable=var,width=7).pack(side='left')
        ttk.Button(roi,text='框选区域',command=self.select_region).pack(side='left',padx=8)
        ttk.Button(roi,text='导入区域 JSON',command=self.load_roi).pack(side='left')
        params=ttk.Frame(root,padding=(12,0,12,8)); params.pack(fill='x')
        self.params={}
        for key,label in [('h_min','H 下限'),('h_max','H 上限'),('s_min','S 下限'),('v_min','V 下限'),('min_pixels','最少像素')]:
            ttk.Label(params,text=label).pack(side='left',padx=4)
            var=tk.StringVar(value=str(self.config[key])); self.params[key]=var
            ttk.Entry(params,textvariable=var,width=6).pack(side='left')
        timing=ttk.Frame(root,padding=(12,0,12,8)); timing.pack(fill='x')
        self.interval=tk.StringVar(value=str(self.config['interval_ms']))
        self.confirm_frames=tk.StringVar(value=str(self.config['confirm_frames']))
        ttk.Label(timing,text='采样间隔（ms）').pack(side='left',padx=4)
        ttk.Spinbox(timing,from_=10,to=100,increment=1,textvariable=self.interval,width=7).pack(side='left')
        ttk.Label(timing,text='确认帧数').pack(side='left',padx=8)
        ttk.Spinbox(timing,from_=1,to=3,increment=1,textvariable=self.confirm_frames,width=5).pack(side='left')
        self.target_rate=tk.StringVar()
        ttk.Label(timing,textvariable=self.target_rate).pack(side='left',padx=16)
        self.interval.trace_add('write',self.update_target_rate)
        self.update_target_rate()
        actions=ttk.Frame(root,padding=12); actions.pack(fill='x')
        ttk.Button(actions,text='开始预览',command=self.start).pack(side='left')
        ttk.Button(actions,text='启用输出',command=self.arm).pack(side='left',padx=8)
        ttk.Button(actions,text='停止',command=self.halt).pack(side='left')
        ttk.Button(actions,text='保存参数',command=self.save_config).pack(side='right')
        previews=ttk.Frame(root,padding=12); previews.pack(fill='both',expand=True)
        previews.columnconfigure(0,weight=1); previews.columnconfigure(1,weight=1)
        ttk.Label(previews,text='采集区域').grid(row=0,column=0)
        ttk.Label(previews,text='颜色掩膜').grid(row=0,column=1)
        self.preview=ttk.Label(previews,anchor='center'); self.preview.grid(row=1,column=0,sticky='nsew')
        self.mask=ttk.Label(previews,anchor='center'); self.mask.grid(row=1,column=1,sticky='nsew')
        previews.rowconfigure(1,weight=1)
        ttk.Label(root,textvariable=self.stats,padding=12).pack(fill='x')
        ttk.Label(root,textvariable=self.costs,padding=(12,0,12,0)).pack(fill='x')
        ttk.Label(root,textvariable=self.status,padding=12,wraplength=850).pack(fill='x')
        self.run_config=None
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(50,self.poll)

    def update_target_rate(self, *args):
        try:
            interval,_=validate_timing(self.interval.get(),1)
            self.target_rate.set(f'设定目标：{1000/interval:.1f} Hz')
        except (ValueError,TypeError):
            self.target_rate.set('设定目标：—')

    def read_config(self):
        cfg=dict(self.config)
        cfg['roi']={k:int(v.get()) for k,v in self.fields.items()}
        cfg.update({k:float(v.get()) for k,v in self.params.items()})
        cfg['interval_ms'],cfg['confirm_frames']=validate_timing(self.interval.get(),self.confirm_frames.get())
        cfg['monitor']=self.monitor.current(); cfg['port']=self.port.get().strip()
        r=self.monitors[cfg['monitor']]; a=cfg['roi']
        if not (0<=a['x']<r[2]-r[0] and 0<=a['y']<r[3]-r[1] and
                0<a['width']<=r[2]-r[0]-a['x'] and 0<a['height']<=r[3]-r[1]-a['y']):
            raise ValueError('区域必须位于所选显示器内')
        if not (0<=cfg['h_min']<=cfg['h_max']<=179 and 0<=cfg['s_min']<=255 and
                0<=cfg['v_min']<=255 and 1<=cfg['min_pixels']<=a['width']*a['height']):
            raise ValueError('颜色参数或像素数量无效')
        return cfg

    def save_config(self):
        try:
            cfg=self.read_config()
            (BASE/'config.json').write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
            self.config=cfg; self.status.set('参数已保存；重新开始预览后生效')
        except Exception as exc: messagebox.showerror('参数错误',str(exc))

    def load_roi(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo('正在运行','先停止预览再更改区域'); return
        path=filedialog.askopenfilename(filetypes=[('JSON','*.json')])
        if path:
            try:
                data=json.loads(Path(path).read_text(encoding='utf-8'))
                for key in self.fields: self.fields[key].set(str(data['roi'][key]))
                self.read_config()
            except Exception as exc: messagebox.showerror('导入失败',str(exc))

    def select_region(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo('正在运行','先停止预览再框选'); return
        rect=self.monitors[self.monitor.current()]
        self.root.withdraw()
        def capture():
            try:
                shot=ImageGrab.grab(bbox=rect,all_screens=True).convert('RGB')
                win=tk.Toplevel(self.root); win.title('框选区域')
                scale=min(1000/shot.width,650/shot.height,1)
                size=(int(shot.width*scale),int(shot.height*scale))
                canvas=tk.Canvas(win,width=size[0],height=size[1],highlightthickness=0)
                canvas.pack(); photo=ImageTk.PhotoImage(shot.resize(size)); canvas.photo=photo
                canvas.create_image(0,0,image=photo,anchor='nw'); start=[]
                def begin(e): start[:]=[e.x,e.y]
                def drag(e):
                    if not start:return
                    canvas.delete('box'); canvas.create_rectangle(*start,e.x,e.y,outline='#00c890',width=2,tags='box')
                def end(e):
                    if not start:return
                    x0,x1=sorted((max(0,min(shot.width,round(start[0]/scale))),max(0,min(shot.width,round(e.x/scale)))))
                    y0,y1=sorted((max(0,min(shot.height,round(start[1]/scale))),max(0,min(shot.height,round(e.y/scale)))))
                    if x1>x0 and y1>y0:
                        for k,v in zip(('x','y','width','height'),(x0,y0,x1-x0,y1-y0)): self.fields[k].set(str(v))
                        win.destroy()
                canvas.bind('<Button-1>',begin); canvas.bind('<B1-Motion>',drag); canvas.bind('<ButtonRelease-1>',end)
            except Exception as exc: messagebox.showerror('截图失败',str(exc))
            finally: self.root.deiconify()
        self.root.after(3000,capture)

    def publish(self, item):
        try: self.events.put_nowait(item)
        except queue.Full:
            try:self.events.get_nowait()
            except queue.Empty:pass
            self.events.put_nowait(item)

    def start(self):
        if self.worker and self.worker.is_alive(): return
        try: cfg=self.read_config()
        except Exception as exc: messagebox.showerror('参数错误',str(exc)); return
        self.stop.clear(); self.armed.clear()
        self.run_config=cfg
        serial_enabled=self.connect.get()
        self.serial_enabled=serial_enabled
        self.status.set('正在启动预览')
        self.worker=threading.Thread(target=self.run,args=(cfg,serial_enabled),daemon=True)
        self.worker.start()

    def run(self,cfg,serial_enabled):
        link=None; confirm=Confirmation(); last_armed=False
        rate=FrameRate(); last_publish=0.0
        rect=self.monitors[cfg['monitor']]; a=cfg['roi']
        bbox=(rect[0]+a['x'],rect[1]+a['y'],rect[0]+a['x']+a['width'],rect[1]+a['y']+a['height'])
        try:
            if serial_enabled: link=Link(cfg['port'])
            while not self.stop.is_set():
                begin=time.monotonic()
                actual_hz=rate.record(begin)
                if ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000: # F8: stop only, never arm.
                    self.armed.clear()
                if time.monotonic()-self.alive>0.5: self.armed.clear()
                armed=self.armed.is_set()
                if armed != last_armed: confirm.count=0
                last_armed=armed
                image=ImageGrab.grab(bbox=bbox,all_screens=True).convert('RGB')
                if image.size!=(a['width'],a['height']): raise RuntimeError('显示设置改变，截图尺寸不匹配')
                result=detect(image,cfg)
                capture_ms=(time.monotonic()-begin)*1000
                fresh=capture_ms<100
                detected=confirm.update(result['hit'] and fresh,int(cfg['confirm_frames']))
                if not fresh: raise RuntimeError('采集处理超过 100ms，已停止；请缩小区域或检查截图模式')
                native=False
                serial_ms=0.0
                if link:
                    # Recheck cancellation after capture; never send an old armed decision.
                    serial_begin=time.monotonic()
                    native=link.exchange(1 if detected and self.armed.is_set() and not self.stop.is_set() else 0)
                    serial_ms=(time.monotonic()-serial_begin)*1000
                    if armed and not native:
                        self.armed.clear()
                        raise RuntimeError('B 板原生 USB 未就绪，输出已关闭')
                # Preview refresh is capped independently; every captured frame still updates B.
                if time.monotonic()-last_publish>=0.1:
                    self.publish({'image':image,'result':result,'detected':detected,
                                  'native':native,'serial':link is not None,'armed':self.armed.is_set(),
                                  'fps':actual_hz,'target_hz':1000/cfg['interval_ms'],
                                  'capture_ms':capture_ms,'serial_ms':serial_ms})
                    last_publish=time.monotonic()
                self.stop.wait(max(0,cfg['interval_ms']/1000-(time.monotonic()-begin)))
        except Exception as exc:
            self.publish({'error':str(exc)})
        finally:
            self.armed.clear()
            if link:
                try:link.close()
                except Exception:pass

    def arm(self):
        if not self.worker or not self.worker.is_alive() or not self.serial_enabled:
            messagebox.showinfo('未连接','先勾选连接 B 板并开始预览'); return
        if not messagebox.askokcancel('启用输出','固定屏幕区域命中后会连续点击。切出游戏不会自动识别失焦。\nF8 停止输出，恢复本窗口也会停止。\n三秒后启用，是否继续？'): return
        self.arm_generation+=1; generation=self.arm_generation
        self.root.iconify()
        def enable():
            if generation==self.arm_generation and not self.stop.is_set() and self.worker.is_alive() and self.root.state()=='iconic':
                self.armed.set()
        self.root.after(3000,enable)

    def halt(self):
        self.arm_generation+=1; self.armed.clear(); self.stop.set()
        self.status.set('已请求停止；串口断开时 B 板最迟按租约超时停止')

    def poll(self):
        self.alive=time.monotonic()
        if self.root.state()!='iconic': self.armed.clear()
        try:
            while True:
                data=self.events.get_nowait()
                if 'error' in data:
                    self.status.set(data['error']); continue
                img=data['image']; mask=Image.fromarray((data['result']['mask']*255).astype('uint8'))
                factor=min(400/img.width,230/img.height,8)
                size=(max(1,int(img.width*factor)),max(1,int(img.height*factor)))
                self.photo=ImageTk.PhotoImage(img.resize(size,Image.Resampling.NEAREST))
                self.mask_photo=ImageTk.PhotoImage(mask.resize(size,Image.Resampling.NEAREST))
                self.preview.configure(image=self.photo); self.mask.configure(image=self.mask_photo)
                actual=f"{data['fps']:.1f} Hz" if data['fps'] else '测量中'
                self.stats.set(f"像素：{data['result']['pixels']}   识别：{'命中' if data['detected'] else '未命中'}   目标：{data['target_hz']:.1f} Hz   实际：{actual}")
                self.costs.set(f"采集＋识别：{data['capture_ms']:.1f} ms   串口往返：{data['serial_ms']:.1f} ms")
                self.status.set(f"{'输出已启用' if data['armed'] else '仅预览'} | 串口：{'已连接' if data['serial'] else '未连接'} | B 原生 USB：{'就绪' if data['native'] else '未就绪/未连接'}")
        except queue.Empty: pass
        self.root.after(50,self.poll)

    def close(self):
        self.halt()
        if self.worker: self.worker.join(timeout=1.5)
        self.root.destroy()


if __name__=='__main__':
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    root=tk.Tk(); App(root); root.mainloop()
