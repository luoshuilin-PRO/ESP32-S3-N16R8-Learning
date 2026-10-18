"""HID-Bridge v0.1.2 operations. Importing this module never opens a port."""
import hashlib
import json
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SETTINGS = {"flash_mode": "dio", "flash_freq": "80m", "flash_size": "4MB"}
OFFSETS = {"0x0": "bootloader/bootloader.bin", "0x8000": "partition_table/partition-table.bin", "0x10000": "dual_s3_hid_proxy.bin"}


def sha256(path):
    """Input path; return streaming SHA-256 for backup/package integrity."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_json(path, data):
    """Input path/data; atomically save a UTF-8 report beside the operation."""
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def firmware_plan(root=ROOT):
    """Validate official files/settings; return immutable address/bytes pairs."""
    root = Path(root)
    hashes = json.loads((root / "firmware-hashes.json").read_text(encoding="utf-8"))
    expected_files = set(OFFSETS.values()) | {"flasher_args.json"}
    if set(hashes) != expected_files:
        raise ValueError("固件校验清单文件集合异常")
    for name, expected in hashes.items():
        if sha256(root / "firmware" / name).lower() != expected.lower():
            raise ValueError(f"官方固件校验失败：{name}")
    config = json.loads((root / "firmware/flasher_args.json").read_text(encoding="utf-8"))
    if config["flash_files"] != OFFSETS or config["flash_settings"] != SETTINGS or config["extra_esptool_args"]["chip"] != "esp32s3":
        raise ValueError("烧录清单与固定 v0.1.2 配置不一致")
    return [(int(offset, 16), (root / "firmware" / name).read_bytes()) for offset, name in OFFSETS.items()]


def validate_identity(info):
    """Input identity; stop unsupported chips/security states before any erase."""
    if info.get("chip") != "ESP32-S3":
        raise ValueError("此向导仅支持 ESP32-S3")
    for flag in ("secure_boot", "flash_encryption", "secure_download"):
        if info.get(flag) is not False:
            raise ValueError(f"安全状态 {flag} 未确认关闭，停止普通备份/刷写流程")
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}", info.get("mac", "")):
        raise ValueError("MAC 数据异常")
    if info.get("flash_size") not in (4, 8, 16, 32, 64, 128):
        raise ValueError("Flash 实际容量未识别或小于 4 MB")


class Device:
    """Pinned esptool adapter; a single serial connection owns each operation."""

    def __init__(self, port, baud=460800):
        self.port, self.esp, self.baud = port, None, baud
        self.reset_done = False

    def __enter__(self):
        import esptool
        from esptool import cmds
        if esptool.__version__ != "5.1.0":
            raise RuntimeError("需要固定版本 esptool 5.1.0，请运行 install.cmd")
        self.cmds = cmds
        try:
            self.esp = cmds.detect_chip(port=self.port, baud=115200, connect_attempts=3)
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.esp is not None:
            self.esp._port.close()

    def __exit__(self, *args):
        try:
            if args[0] is None and not self.reset_done:
                self.esp.hard_reset()
        finally:
            self.close()

    def inspect(self):
        """Read chip/security/size; only loads RAM stub, never writes flash/eFuse."""
        esp = self.esp
        if esp.CHIP_NAME != "ESP32-S3" or esp.secure_download_mode:
            raise ValueError("芯片型号或安全下载模式不符合普通刷写条件")
        info = {"chip": esp.CHIP_NAME, "mac": ":".join(f"{b:02x}" for b in esp.read_mac()),
                "secure_download": bool(esp.secure_download_mode),
                "secure_boot": bool(esp.get_secure_boot_enabled()),
                "flash_encryption": bool(esp.get_flash_encryption_enabled())}
        if info["secure_boot"] or info["flash_encryption"]:
            raise ValueError("检测到安全启动或 Flash 加密；保留当前内容并停止")
        self.esp = self.cmds.run_stub(esp)
        self.cmds.attach_flash(self.esp)
        size = self.cmds.detect_flash_size(self.esp)
        if not size or not re.fullmatch(r"\d+MB", size):
            raise ValueError("未识别 Flash 容量")
        info.update(flash_size=int(size[:-2]), port=self.port, flash_id=hex(self.esp.flash_id()))
        validate_identity(info)
        if self.baud not in (115200, 460800):
            raise ValueError("刷写波特率仅支持 115200 / 460800")
        self.esp.change_baud(self.baud)
        info["transfer_baud"] = self.baud
        return info

    def backup(self, path, size):
        self.cmds.read_flash(self.esp, 0, size, str(path), flash_size=f"{size // (1024 * 1024)}MB")

    def verify(self, segments, settings=None):
        self.cmds.verify_flash(self.esp, segments, **(settings or {}))

    def erase(self):
        self.cmds.erase_flash(self.esp)

    def write(self, segments, settings=None):
        self.cmds.write_flash(self.esp, segments, **(settings or {}))

    def boot_log(self, seconds=10):
        """Reset then capture UART without reopening/toggling the port again."""
        port = self.esp._port
        port.baudrate, port.timeout = 115200, 0.2
        port.reset_input_buffer()
        self.esp.hard_reset()
        self.reset_done = True
        chunks, end = [], time.monotonic() + seconds
        while time.monotonic() < end:
            chunks.append(port.read(min(max(port.in_waiting, 1), 8192)))
        return b"".join(chunks)


def backup_board(device, info, label, folder):
    """Create full-capacity backup and verify against device; return metadata path."""
    validate_identity(info)
    if label not in ("A", "B"):
        raise ValueError("板卡标签应为 A 或 B")
    name = f"{label}-{info['mac'].replace(':', '')}-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    directory = Path(folder) / name
    directory.mkdir(parents=True, exist_ok=False)
    binary = directory / "flash.bin"
    size = info["flash_size"] * 1024 * 1024
    device.backup(binary, size)
    if binary.stat().st_size != size:
        raise ValueError("备份字节数与实际 Flash 容量不一致，停止")
    device.verify([(0, binary.read_bytes())])
    metadata = {"schema": 1, "board": label, "identity": info, "bytes": size,
                "sha256": sha256(binary), "verified": True, "file": "flash.bin"}
    path = directory / "backup.json"
    save_json(path, metadata)
    return path


def load_backup(path, info):
    """Require exact MAC/capacity and verified hash; return raw restore bytes."""
    validate_identity(info)
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or data.get("verified") is not True or data.get("file") != "flash.bin":
        raise ValueError("不是本工具已验证的整片备份")
    for key in ("chip", "mac", "flash_size"):
        if data.get("identity", {}).get(key) != info[key]:
            raise ValueError(f"备份与当前板卡 {key} 不匹配")
    binary = path.parent / "flash.bin"
    payload = binary.read_bytes()
    if len(payload) != info["flash_size"] * 1024 * 1024 or data.get("bytes") != len(payload):
        raise ValueError("备份长度异常")
    if hashlib.sha256(payload).hexdigest() != data.get("sha256"):
        raise ValueError("备份 SHA-256 校验失败")
    return payload


def program(device, info, label, backup_folder, segments, settings, confirm):
    """Always back up first; confirm then erase/write/verify in the same session."""
    validate_identity(info)
    if not segments or settings not in ({}, SETTINGS):
        raise ValueError("写入计划参数异常")
    end = 0
    for address, payload in sorted(segments):
        if address < end or address % 4096 or not isinstance(payload, bytes) or not payload:
            raise ValueError("写入区间为空、重叠或未对齐")
        end = address + len(payload)
        if end > info["flash_size"] * 1024 * 1024:
            raise ValueError("写入区间超过实际容量")
    backup = backup_board(device, info, label, backup_folder)
    print(f"完整备份已验证：{backup}")
    if not confirm():
        return {"status": "cancelled", "backup": str(backup), "written": False}
    report = {"status": "erase_started", "backup": str(backup), "written": False,
              "identity": info, "passthrough": "待用户接线测试"}
    report_path = backup.parent / "operation.json"
    save_json(report_path, report)
    try:
        device.erase()
        report["status"] = "write_started"
        save_json(report_path, report)
        device.write(segments, settings)
        report["status"] = "verify_started"
        save_json(report_path, report)
        device.verify(segments, settings)
        report.update(status="flash_verified", written=True)
    except BaseException as error:
        report.update(status="failed", error=str(error))
        save_json(report_path, report)
        raise
    save_json(report_path, report)
    return report


def assess_boot(raw):
    """Classify UART evidence only, never equate it with successful HID passthrough."""
    text = raw.decode("utf-8", errors="replace")
    if re.search(r"Guru Meditation|panic'ed|abort\(\)|invalid header|invalid magic|flash read err", text, re.I) or len(re.findall(r"rst:0x", text)) > 1:
        return "启动日志出现异常或重复复位，需检查"
    if "dual_s3_hid_proxy" in text and re.search(r"Calling app_main|Returned from app_main", text):
        return "捕获到目标应用启动证据；双板角色和透传待接线验证"
    return "未取得充分启动证据；写入校验结果独立有效，启动状态待确认"
