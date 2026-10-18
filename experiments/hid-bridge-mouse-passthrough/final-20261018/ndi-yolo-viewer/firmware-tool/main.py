"""Chinese console wizard. No port is opened until isolation is confirmed."""
import argparse
import contextlib
import sys
from datetime import datetime
from pathlib import Path
from serial.tools import list_ports
from flasher import ROOT, SETTINGS, Device, firmware_plan, backup_board, load_backup, program, assess_boot, save_json


class Tee:
    def __init__(self, screen, logfile):
        self.screen, self.logfile = screen, logfile

    def write(self, text):
        self.screen.write(text)
        self.logfile.write(text)
        self.logfile.flush()
        return len(text)

    def flush(self):
        self.screen.flush()
        self.logfile.flush()

    def isatty(self):
        return False


def confirmed(token):
    """Require a displayed exact phrase; Enter alone always cancels."""
    return input(f"输入 {token} 确认（回车取消）：").strip() == token


def main():
    parser = argparse.ArgumentParser(description="HID-Bridge v0.1.2 备份/烧录/恢复向导")
    parser.add_argument("--self-check", action="store_true", help="只检查依赖和固件，不扫描或连接设备")
    args = parser.parse_args()
    segments = firmware_plan()
    import esptool
    if esptool.__version__ != "5.1.0":
        raise RuntimeError("请运行 install.cmd 安装固定版本 esptool 5.1.0")
    print("官方 v0.1.2 镜像校验通过：A/B 使用同一份；DIO / 80 MHz / 4 MB。")
    if args.self_check:
        print("SELF-CHECK PASS（没有连接设备）")
        return
    print("1 检查板卡   2 完整备份   3 备份并烧录 v0.1.2   4 恢复本工具备份   0 退出")
    action = input("选择：").strip()
    if action not in ("1", "2", "3", "4"):
        return
    label = input("当前板卡标签 A（鼠标侧）或 B（电脑侧）：").strip().upper()
    if label not in ("A", "B"):
        raise ValueError("请选择 A 或 B")
    ports = sorted(list_ports.comports(), key=lambda port: port.device)
    if not ports:
        raise RuntimeError("没有发现串口，请检查 COM 数据线和对应的 WCH 驱动")
    for i, port in enumerate(ports, 1):
        print(f"{i}: {port.device}  {port.description}  {port.hwid}")
    number = int(input("输入串口序号："))
    if not 1 <= number <= len(ports):
        raise ValueError("串口序号超出范围")
    port = ports[number - 1].device
    baud = int(input("备份/刷写传输波特率 460800 或 115200（回车=460800）：").strip() or "460800")
    if baud not in (115200, 460800):
        raise ValueError("请选择 460800 或 115200")
    print("断电拆除鼠标、原生 USB、外接电源和所有板间线；仅当前板的 COM 接电脑。")
    print("关闭识别/诊断/串口工具。检查步骤会复位板子进入下载模式。")
    print("A 的背部 OTG 供电焊盘由人工核对；B 保持未短接。软件不检测焊点。")
    if not confirmed("ISOLATED"):
        return
    restore_path = None
    if action == "4":
        restore_path = Path(input("粘贴 backup.json 完整路径：").strip().strip('"'))
    with Device(port, baud) as device:
        info = device.inspect()
        print(f"板卡 {label} / {port} / {info['chip']} / MAC {info['mac']} / 实际 Flash {info['flash_size']} MB")
        registry_path = ROOT / "boards.json"
        registry = {}
        if registry_path.exists():
            import json
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        previous = registry.get(label)
        if previous and previous != info["mac"]:
            print(f"注意：上次 {label} 的 MAC 是 {previous}，当前是另一块板。")
        if not confirmed(f"BOARD {label} {info['mac']}"):
            return
        registry[label] = info["mac"]
        save_json(registry_path, registry)
        save_json(ROOT / "logs" / "last-identity.json", info)
        if action == "1":
            print("芯片、容量及普通刷写安全状态检查通过；未更改 Flash。")
            return
        if action == "2":
            print(f"已完成整片备份和板端内容校验：{backup_board(device, info, label, ROOT / 'backups')}")
            return
        if action == "4":
            segments, settings = [(0, load_backup(restore_path, info))], {}
            token = f"RESTORE {label} {info['mac']}"
        else:
            settings = SETTINGS
            token = f"FLASH {label} {info['mac']}"
        print("现在先备份当前完整 Flash 并验证。之后才会询问整片擦除/写入确认。")
        report = program(device, info, label, ROOT / "backups", segments, settings, lambda: confirmed(token))
        if not report["written"]:
            print("已取消写入，备份已保留。")
            return
        print("Flash 写入与独立读回摘要校验通过。接下来复位采集 10 秒启动日志。")
        report_path = Path(report["backup"]).parent / "operation.json"
        try:
            raw = device.boot_log()
            (report_path.parent / "boot.log").write_bytes(raw)
            report["boot"] = assess_boot(raw)
        except Exception as error:
            report["boot"] = "启动采集失败，待确认：" + str(error)
        save_json(report_path, report)
        print(report["boot"])
        print("板间协商、kmbox/Makcu、鼠标透传均需另行接线测试，不在本次隔离烧录中判定通过。")
        print("断开电源后接 A17→B18、A18→B17、GND↔GND，不互接5V/3.3V。")
        print("鼠标→A USB，A COM→控制电脑，B USB→接收鼠标的电脑。详见 README.md。")


if __name__ == "__main__":
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    logfile = logs / f"wizard-{datetime.now():%Y%m%d-%H%M%S}.log"
    code = 0
    with logfile.open("a", encoding="utf-8") as output:
        with contextlib.redirect_stdout(Tee(sys.stdout, output)), contextlib.redirect_stderr(Tee(sys.stderr, output)):
            try:
                main()
            except (Exception, KeyboardInterrupt) as error:
                print(f"操作停止：{type(error).__name__}: {error}")
                print("若已开始擦除/写入，请保持供电，关闭本工具后按原流程重新连接，使用已保存备份恢复或重刷。")
                print("连接失败可按住 BOOT、点按 RST 再松开 BOOT；端口被占用时先关闭其他程序。")
                code = 1
    print(f"日志：{logfile}")
    raise SystemExit(code)
