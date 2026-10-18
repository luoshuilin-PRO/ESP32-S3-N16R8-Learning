"""独立固件/串口诊断 GUI；默认不连接、不输出输入、不自动复位。"""
import datetime
import json
import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox,scrolledtext
from serial.tools import list_ports
from checks import diagnose,kmbox,boot_log,active_test,row,set_device_baud

ROOT=Path(__file__).parent


class App:
    def __init__(self,root):
        self.root=root
        root.title("ESP32-S3 HID-Bridge 诊断")
        root.geometry("1040x740")
        root.minsize(850,600)
        menu=tk.Menu(root)
        help_menu=tk.Menu(menu,tearoff=False)
        help_menu.add_command(label="使用说明",command=self.help)
        menu.add_cascade(label="帮助",menu=help_menu)
        root.config(menu=menu)
        self.config=json.loads((ROOT/"config.json").read_text(encoding="utf-8"))
        self.events=queue.Queue()
        self.stop=threading.Event()
        self.worker=None
        self.closing=False
        self.reports=[]
        self.buttons=[]
        top=ttk.Frame(root,padding=8)
        top.pack(fill="x")
        self.port=ttk.Combobox(top,state="readonly",width=14)
        self.port.pack(side="left")
        self.button(top,"刷新端口",self.refresh)
        ttk.Label(top,text="PC 波特率").pack(side="left",padx=5)
        self.baud=ttk.Combobox(top,state="readonly",values=self.config["baud_choices"],width=12)
        self.baud.set(115200)
        self.baud.pack(side="left")
        self.button(top,"只读诊断",self.diagnose)
        self.button(top,"启动版本（复位）",self.boot)
        ttk.Button(top,text="停止",command=self.stop.set).pack(side="left",padx=5)
        actions=ttk.Frame(root,padding=(8,0,8,8))
        actions.pack(fill="x")
        self.button(actions,"小幅移动测试",lambda:self.active("move"))
        self.button(actions,"单击测试",lambda:self.active("click"))
        self.button(actions,"主机事件窗口",self.viewer)
        self.button(actions,"保存报告",self.save)
        ttk.Label(actions,text="M 设备改速").pack(side="left",padx=5)
        self.target_baud=ttk.Combobox(actions,state="readonly",values=(115200,4000000),width=10)
        self.target_baud.set(115200)
        self.target_baud.pack(side="left")
        self.button(actions,"确认改速",self.change_baud)
        udp=ttk.Frame(root,padding=(8,0,8,8))
        udp.pack(fill="x")
        ttk.Label(udp,text="Host UDP").pack(side="left")
        self.host=ttk.Entry(udp,width=22)
        self.host.insert(0,self.config["udp_host"])
        self.host.pack(side="left",padx=4)
        self.udp_port=ttk.Entry(udp,width=7)
        self.udp_port.insert(0,str(self.config["udp_port"]))
        self.udp_port.pack(side="left")
        ttk.Label(udp,text="UUID").pack(side="left",padx=4)
        self.uuid=ttk.Entry(udp,width=12)
        self.uuid.insert(0,self.config["udp_uuid"])
        self.uuid.pack(side="left")
        self.button(udp,"kmboxNet 握手",self.udp)
        self.status=tk.StringVar(value="默认未连接；检测时关闭其他串口客户端")
        ttk.Label(root,textvariable=self.status,padding=8).pack(anchor="w")
        self.tree=ttk.Treeview(root,columns=("name","status","detail"),show="headings",height=13)
        for key,text,width in (("name","项目",210),("status","结论",85),("detail","证据／边界",660)):
            self.tree.heading(key,text=text)
            self.tree.column(key,width=width)
        self.tree.pack(fill="both",expand=True,padx=8)
        self.log=scrolledtext.ScrolledText(root,height=9,state="disabled")
        self.log.pack(fill="both",expand=True,padx=8,pady=8)
        root.protocol("WM_DELETE_WINDOW",self.close)
        self.refresh()
        root.after(50,self.poll)

    def button(self,parent,text,command):
        b=ttk.Button(parent,text=text,command=command)
        b.pack(side="left",padx=4)
        self.buttons.append(b)

    def help(self):
        """展示随工具保存的中文步骤，不打开串口或执行检测。"""
        window=tk.Toplevel(self.root)
        window.title("检测工具使用说明")
        window.geometry("800x650")
        text=scrolledtext.ScrolledText(window,wrap="word",padx=12,pady=12)
        text.pack(fill="both",expand=True)
        try:
            content=(ROOT/"使用说明.md").read_text(encoding="utf-8")
        except OSError as error:
            content=f"读取说明失败：{error}"
        text.insert("end",content)
        text.configure(state="disabled")

    def refresh(self):
        ports=list(list_ports.comports())
        self.port["values"]=[p.device for p in ports]
        self.port.set("")
        self.events.put(("log","\n".join(f"{p.device}: {p.description} | {p.hwid}" for p in ports)))

    def selected(self):
        if not self.port.get():
            raise ValueError("请选择实际端口")
        return self.port.get(),int(self.baud.get())

    def submit(self,function):
        if self.worker and self.worker.is_alive() or self.closing:
            return
        self.stop.clear()
        for b in self.buttons:
            b["state"]="disabled"
        self.status.set("检测进行中；不会自动进行下一项")
        def work():
            try:
                report=function()
            except Exception as error:
                report={"checks":[row("本轮检测","失败",str(error))]}
            report["time"]=datetime.datetime.now().astimezone().isoformat()
            self.events.put(("report",report))
        self.worker=threading.Thread(target=work,daemon=False)
        self.worker.start()

    def diagnose(self):
        try:
            port,baud=self.selected()
            if messagebox.askyesno("只读查询", "先关闭 Host、NDI 控制软件及其他 COM 工具。\n查询不注入鼠标、不复位，但会切换软件输入所有者。\n开始诊断？"):
                self.submit(lambda:diagnose(port,baud,self.config,lambda s:self.events.put(("log",s)),self.stop))
        except ValueError as error:
            messagebox.showerror("参数",str(error))

    def boot(self):
        try:
            port,_=self.selected()
            if messagebox.askyesno("显式复位", "仅在板子隔离、只接 COM 时使用。\n本操作会复位板子，中断透传并清空 RAM 统计。\n确认已隔离并读取启动版本？"):
                self.submit(lambda:boot_log(port,self.stop,lambda s:self.events.put(("log",s))))
        except ValueError as error:
            messagebox.showerror("参数",str(error))

    def active(self,action):
        try:
            port,baud=self.selected()
            name="小幅右移再左移" if action=="move" else "左键单击一次"
            if messagebox.askyesno("确认主动输入",f"双板接好，目标主机打开空白事件窗口并松开物理按钮。\n本次会发送：{name}。\n确认？"):
                self.submit(lambda:active_test(port,baud,action,self.stop,lambda s:self.events.put(("log",s))))
        except ValueError as error:
            messagebox.showerror("参数",str(error))

    def udp(self):
        try:
            host,port,uuid=self.host.get().strip(),int(self.udp_port.get()),self.uuid.get().strip()
            if messagebox.askyesno("UDP 握手", "需要 Host 软件运行且 UDP 接口开启。\n只发送 init，不发送输入；它会登记 UDP 会话。\n确认测试？"):
                self.submit(lambda:kmbox(host,port,uuid))
        except ValueError as error:
            messagebox.showerror("参数",str(error))

    def change_baud(self):
        try:
            port,current=self.selected()
            target=int(self.target_baud.get())
            if messagebox.askyesno("设备改速",f"只适用于已锁定 M 角色的板卡，会改变串口通信速率。\n4M 曾在 CH340 驱动失败，不保证支持。\n失败可能需隔离后复位，不能保证自动回滚。\n确认从 {current} 改为 {target}？"):
                self.submit(lambda:set_device_baud(port,current,target,lambda s:self.events.put(("log",s)),self.stop))
        except ValueError as error:
            messagebox.showerror("参数",str(error))

    def viewer(self):
        """目标主机上的事件观察窗口，只记录系统实际送达的 Tk 事件。"""
        window=tk.Toplevel(self.root)
        window.title("目标主机鼠标事件观察")
        window.geometry("650x430")
        text=tk.StringVar(value="请在实际接 B 板 USB 的主机运行此窗口")
        ttk.Label(window,textvariable=text,padding=12).pack()
        canvas=tk.Canvas(window,bg="#eef2f3")
        canvas.pack(fill="both",expand=True)
        counters={"move":0,"left":0,"left_up":0,"middle":0,"middle_up":0,"right":0,"right_up":0,"wheel_up":0,"wheel_down":0}
        def record(name,event):
            counters[name]+=1
            text.set(str(counters))
        canvas.bind("<Motion>",lambda e:record("move",e))
        for n,name in ((1,"left"),(2,"middle"),(3,"right")):
            canvas.bind(f"<ButtonPress-{n}>",lambda e,name=name:record(name,e))
            canvas.bind(f"<ButtonRelease-{n}>",lambda e,name=name:record(name+"_up",e))
        canvas.bind("<MouseWheel>",lambda e:record("wheel_up" if e.delta>0 else "wheel_down",e))
        def confirm():
            if messagebox.askyesno("人工验收", "确认此窗口在目标主机运行，输入由桥接鼠标产生，且未混入其他鼠标？\n侧键需另行在浏览器测试，当前窗口不验证侧键。"):
                items=[row("目标端 "+name+"（人工来源确认）","通过" if value>0 else "未验证",f"事件 {value} 次") for name,value in counters.items()]
                items.append(row("侧键／游戏消费","未验证","Tk 事件窗口不覆盖这些场景"))
                self.events.put(("report",{"time":datetime.datetime.now().astimezone().isoformat(),"checks":items}))
        ttk.Button(window,text="记录人工验收",command=confirm).pack(pady=8)

    def save(self):
        directory=ROOT/"reports"
        directory.mkdir(exist_ok=True)
        path=directory/(datetime.datetime.now().strftime("%Y%m%d-%H%M%S")+".json")
        path.write_text(json.dumps({"tool_schema":1,"reports":self.reports},ensure_ascii=False,indent=2),encoding="utf-8")
        self.status.set(f"报告已保存：{path.name}")

    def poll(self):
        while not self.events.empty():
            kind,value=self.events.get()
            if kind=="log":
                self.log.configure(state="normal")
                self.log.insert("end",str(value)+"\n")
                self.log.see("end")
                self.log.configure(state="disabled")
            else:
                self.reports.append(value)
                for item in value["checks"]:
                    self.tree.insert("","end",values=(item["name"],item["status"],str(item["detail"])))
                for b in self.buttons:
                    b["state"]="normal"
                self.status.set("本轮完成；每项结论有独立证据边界")
        if self.closing and (self.worker is None or not self.worker.is_alive()):
            self.root.destroy()
            return
        self.root.after(50,self.poll)

    def close(self):
        self.closing=True
        self.stop.set()


if __name__=="__main__":
    root=tk.Tk()
    App(root)
    root.mainloop()
