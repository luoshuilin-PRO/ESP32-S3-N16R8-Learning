"""独立诊断动作；默认查询，主动输入、设备改速和复位由界面单独确认。"""
import json
import re
import secrets
import socket
import struct
import time
from pathlib import Path
from controller import Controller
from makcu_transport import Transport
from protocol import Scanner
from stats_reference import SnapshotCollector


def row(name,status,detail):
    """输出统一报告项目，status 为通过、失败、未验证或不适用。"""
    return {"name":name,"status":status,"detail":detail}


def snapshot(c, timeout):
    """输入已打开控制器，输出经过页数、字段、角色和 uptime 校验的完整统计。"""
    seq=c.send(0x1D)
    collector=SnapshotCollector()
    for kind,sequence,payload in c.responses(timeout):
        if kind==0x1E and sequence==seq:
            collector.add(payload)
            if collector.complete:
                return collector.result()
    raise TimeoutError("统计快照缺页")


def compare(first,second,elapsed):
    """比较 uptime 和计数，不把板端活动误判为电脑已收到鼠标。"""
    delta=second["uptimeMilliseconds"]-first["uptimeMilliseconds"]
    continuity=first["roleId"]==second["roleId"] and delta>=0 and abs(delta-elapsed*1000)<1500
    counters={k:second["counters"][k]-v for k,v in first["counters"].items() if k in second["counters"]}
    activity=counters.get("uart1_tx",0)>0 and counters.get("uart1_rx",0)>0
    return continuity,activity,counters


def diagnose(port,baud,config,log,stop):
    """输入指定串口、速率、配置，执行 A5 查询后一次切到 V4，返回完整报告。"""
    results=[]
    report={"port":port,"host_baud":baud,"checks":results,"snapshots":[]}
    c=Controller(log)
    try:
        if stop.is_set():
            raise InterruptedError("用户停止，未连接")
        c.connect(port,baud)
        results.append(row("串口打开","通过","已打开；DTR/RTS 在 open 前后置低"))
        role=c.probe()
        role_name={0:"UNRESOLVED",1:"P/PC_DEVICE",2:"M/MOUSE_HOST"}.get(role,"未知")
        results.append(row("固件协议／角色","通过",f"HIDBRDG2 nonce/序号匹配，角色 {role_name}；非 MAC 认证"))
        results.append(row("PC 波特率通信","通过",f"{baud} 下收到 CRC 合法响应；仅证明该 COM 链路"))
        results.append(row("精确固件版本","未验证","协议签名和 API 级别不是 v0.1.2 版本号，可隔离后读取启动日志"))
        if role not in (1,2):
            results.append(row("板间／透传","不适用","隔离无 USB/鼠标时身份未定属预期；接好双板才能测透传"))
            results.append(row("Makcu","不适用","必须先锁定 M 角色"))
            return report
        first=snapshot(c,config["query_timeout_seconds"])
        begin=time.monotonic()
        log("统计第一份完成；可手动移动真实鼠标，工具不注入输入")
        if stop.wait(config["snapshot_gap_seconds"]):
            raise InterruptedError("用户停止")
        second=snapshot(c,config["query_timeout_seconds"])
        continuity,activity,diff=compare(first,second,time.monotonic()-begin)
        report["snapshots"]=[first,second]
        report["counter_delta"]=diff
        results.append(row("查询期间 uptime 连续","通过" if continuity else "失败",f"{first['uptimeMilliseconds']} → {second['uptimeMilliseconds']}ms；不证明首次打开前未复位"))
        results.append(row("板间 UART 双向活动","通过" if activity else "未验证",f"TX +{diff.get('uart1_tx',0)}，RX +{diff.get('uart1_rx',0)}；有活动不等于 HID 已消费"))
        errors={k:v for k,v in diff.items() if v>0 and k in ("uart1_tx_write_fail","uart1_rx_overflow","uart1_frame_err","transfer_fail","failed","errors","input_fail")}
        results.append(row("观察窗口新增错误","失败" if errors else "通过",errors or "所读计数未见新增错误，不代表长时稳定"))
        report["queue_snapshot"]=second["queues"]
        if role==1:
            state=second["state"]
            results.append(row("P USB 克隆／挂载","通过" if state.get("cloneActive") and state.get("mounted") else "未验证",state))
            results.append(row("Makcu","不适用","Makcu 鼠标 API 在 M 维护口，不在 P 口"))
        else:
            c.close()
            # 新串口打开仍保持 DTR/RTS 低；一次 V4 切换不与 A5 来回争用。
            v=Transport(log)
            try:
                v.connect(port,baud)
                tests=((0x02,b"\x01","设备类型"),(0x04,struct.pack("<I",4),"API 级别"),
                       (0xA4,struct.pack("<I",baud),"设备波特率"))
                for opcode,expected,name in tests:
                    if stop.is_set():
                        raise InterruptedError("用户停止")
                    actual=v.query(opcode)
                    results.append(row("Makcu "+name,"通过" if actual==expected else "失败",actual.hex()))
                for opcode,name,valid in ((0x55,"物理按钮",lambda b:len(b)==1 and b[0]<=31),
                                         (0x56,"软件状态快照",lambda b:len(b)==40),
                                         (0x1F,"插值查询",lambda b:len(b)==1 and (b[0]<=100 or b[0]==255)),
                                         (0x64,"屏幕参数",lambda b:len(b)==4),
                                         (0x66,"移动状态",lambda b:len(b)==1 and b[0]<=1)):
                    actual=v.query(opcode)
                    results.append(row("Makcu "+name,"通过" if valid(actual) else "失败",actual.hex()))
            finally:
                v.close()
        results.append(row("主机实际鼠标透传","未验证","请在目标主机的事件窗口验收移动、左/右/中键、滚轮，侧键单独人工确认"))
        results.append(row("kmboxNet","未验证","需要单独测试运行中的 Host UDP 服务，不属于板卡串口固件自带端口"))
    except Exception as error:
        results.append(row("本轮诊断","失败",str(error)))
    finally:
        c.close()
    return report


def kmbox(host,port,uuid,timeout=2):
    """仅发送 init 握手，不发送鼠标、键盘或屏蔽命令；返回 ACK 校验结果。"""
    if not re.fullmatch(r"[0-9a-fA-F]{8}",uuid):
        raise ValueError("UUID 必须为 8 位十六进制")
    mac=int(uuid,16)
    if not 0<=mac<=0xFFFFFFFF or not 1<=port<=65535:
        raise ValueError("UUID 或 UDP 端口非法")
    ip=socket.gethostbyname(host)
    packet=struct.pack("<IIII",mac,secrets.randbits(32),secrets.randbits(32),0xaf3c2828)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(packet,(ip,port))
        received,sender=sock.recvfrom(1024)
    valid=sender==(ip,port) and received==packet
    return {"checks":[row("kmboxNet init","通过" if valid else "失败",f"来源 {sender}，ACK {received.hex()}；不证明 HID 输出或完整 kmNet API")],"udp_endpoint":[ip,port]}


def boot_log(port,stop,log):
    """显式复位入口；输入串口，输出原始启动日志和版本，需用户隔离且确认。"""
    c=Controller(log)
    raw=bytearray()
    try:
        if stop.is_set():
            raise InterruptedError("用户停止，未复位")
        c.connect(port,921600)
        if stop.is_set():
            raise InterruptedError("用户停止，未复位")
        c.port.rts=True
        time.sleep(.1)
        c.port.rts=False
        deadline=time.monotonic()+8
        while time.monotonic()<deadline and not stop.is_set():
            data=c.port.read(4096)
            raw.extend(data)
        text=raw.decode("utf-8",errors="replace")
        versions=re.findall(r"App version:\s*([^\r\n]+)",text)
        idf=re.findall(r"ESP-IDF:\s*([^\r\n]+)",text)
        return {"checks":[row("启动日志版本","通过" if versions else "未验证",{"app":versions,"idf":idf,"explicit_reset":True})],"boot_text":text,"boot_raw_hex":raw.hex()}
    finally:
        c.close()


def active_test(port,baud,action,stop,log):
    """单独确认后的 +4/-4 或一次点击，异常也释放；仅调用 V4 子集。"""
    c=Transport(log)
    try:
        if stop.is_set():
            raise InterruptedError("用户停止，未发送输入")
        c.connect(port,baud)
        if stop.is_set():
            raise InterruptedError("用户停止，未发送输入")
        if action=="move":
            c.report(0,4,0)
            if not stop.wait(.25):
                c.report(0,-4,0)
        elif action=="click":
            c.report(1,0,0)
            stop.wait(.05)
        else:
            raise ValueError("未知动作")
        c.release()
        return {"checks":[row("主动输入写入","通过","命令已写入，SET 无成功 ACK"),row("主机消费","未验证","必须目标主机观察确认，不能由串口写入推断")],"action":action}
    finally:
        c.close()


def set_device_baud(port,current,target,log,stop=None):
    """显式确认后的 M 设备改速；先检查 PC 驱动，失败不自动复位或猜测回滚。"""
    if target not in (115200,4000000):
        raise ValueError("该固件 M 端只支持 115200／4000000，P 端不适用")
    c=Transport(log)
    changed=False
    try:
        if stop is not None and stop.is_set():
            raise InterruptedError("用户停止，未改速")
        c.connect(port,current)
        # 先验证驱动是否接受，尚未发送设备改速命令。
        c.port.baudrate=target
        c.port.baudrate=current
        if stop is not None and stop.is_set():
            raise InterruptedError("用户停止，未改速")
        c.wire(0xA5,struct.pack("<I",target))
        changed=True
        time.sleep(.15)
        c.port.baudrate=target
        response=c.query(0xA4)
        valid=response==struct.pack("<I",target)
        return {"port":port,"checks":[row("设备改速","通过" if valid else "失败",f"请求 {target}，回应 {response.hex()}；仅运行时生效，重启恢复默认")],"requested_baud":target}
    except Exception as error:
        return {"port":port,"checks":[row("设备改速","失败",f"{error}；{'设备可能已改速，状态未知，隔离后显式复位恢复' if changed else '设备改速命令未发送'}")],"device_command_sent":changed}
    finally:
        c.close()
