"""Offline state/backup tests; the fake device never opens a serial port."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from flasher import ROOT, SETTINGS, assess_boot, backup_board, firmware_plan, load_backup, program, validate_identity, save_json

INFO = {"chip": "ESP32-S3", "mac": "00:11:22:33:44:55", "flash_size": 4,
        "secure_boot": False, "flash_encryption": False, "secure_download": False}


class Fake:
    def __init__(self, fail=None):
        self.events, self.fail = [], fail
        self.original = b"\xa5" * (4 * 1024 * 1024)

    def backup(self, path, size):
        self.events.append("backup")
        Path(path).write_bytes(self.original[:10] if self.fail == "short" else self.original)

    def verify(self, segments, settings=None):
        self.events.append("verify")
        if self.fail == "backup_verify" or self.fail == "write_verify" and "write" in self.events:
            raise RuntimeError("verify failure")

    def erase(self):
        self.events.append("erase")
        if self.fail == "erase":
            raise RuntimeError("erase failure")

    def write(self, segments, settings=None):
        self.events.append("write")
        if self.fail == "write":
            raise RuntimeError("write failure")


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_program(self, device, confirm=lambda: True):
        return program(device, INFO, "A", self.folder, [(0, b"test")], SETTINGS, confirm)

    def test_official_image_plan(self):
        self.assertEqual([offset for offset, _ in firmware_plan()], [0, 0x8000, 0x10000])

    def test_tampered_package_rejected(self):
        with patch("flasher.sha256", return_value="0" * 64):
            with self.assertRaises(ValueError):
                firmware_plan()

    def test_unrecognized_security_rejected(self):
        for field in ("secure_boot", "secure_download", "flash_encryption"):
            for value in (True, None):
                with self.subTest(field=field, value=value):
                    info = dict(INFO, **{field: value})
                    with self.assertRaises(ValueError):
                        validate_identity(info)

    def test_wrong_chip_or_capacity(self):
        for change in ({"chip": "ESP32"}, {"flash_size": 2}, {"mac": "bad"}):
            with self.assertRaises(ValueError):
                validate_identity(dict(INFO, **change))

    def test_backup_verified_before_erase(self):
        device = Fake()
        report = self.run_program(device)
        self.assertEqual(device.events, ["backup", "verify", "erase", "write", "verify"])
        self.assertEqual(report["status"], "flash_verified")
        self.assertEqual(load_backup(report["backup"], INFO), device.original)

    def test_cancel_preserves_backup(self):
        device = Fake()
        report = self.run_program(device, lambda: False)
        self.assertEqual(device.events, ["backup", "verify"])
        self.assertFalse(report["written"])
        self.assertTrue(Path(report["backup"]).exists())

    def test_backup_failure_never_erases(self):
        for fail in ("short", "backup_verify"):
            with self.subTest(fail=fail):
                device = Fake(fail)
                with self.assertRaises((ValueError, RuntimeError)):
                    self.run_program(device)
                self.assertNotIn("erase", device.events)

    def test_write_failures_recorded(self):
        for fail in ("erase", "write", "write_verify"):
            with self.subTest(fail=fail):
                device = Fake(fail)
                with self.assertRaises(RuntimeError):
                    self.run_program(device)
                reports = [json.loads(p.read_text(encoding="utf-8")) for p in self.folder.glob("*/operation.json")]
                self.assertTrue(all(r["status"] == "failed" and not r["written"] for r in reports))

    def test_restore_rejects_other_board(self):
        path = backup_board(Fake(), INFO, "A", self.folder)
        for change in ({"mac": "00:11:22:33:44:66"}, {"flash_size": 8}):
            with self.assertRaises(ValueError):
                load_backup(path, dict(INFO, **change))

    def test_restore_rejects_changed_bytes(self):
        path = backup_board(Fake(), INFO, "A", self.folder)
        with (path.parent / "flash.bin").open("r+b") as stream:
            stream.write(b"bad")
        with self.assertRaises(ValueError):
            load_backup(path, INFO)

    def test_restore_rejects_unverified_and_path_escape(self):
        path = backup_board(Fake(), INFO, "A", self.folder)
        data = json.loads(path.read_text())
        for change in ({"verified": False}, {"file": "../flash.bin"}):
            save_json(path, dict(data, **change))
            with self.assertRaises(ValueError):
                load_backup(path, INFO)

    def test_bad_write_plan_never_touches_device(self):
        for segments in ([], [(1, b"x")], [(0, b"")], [(0, b"a" * 8192), (4096, b"b")], [(0x400000, b"x")]):
            device = Fake()
            with self.assertRaises(ValueError):
                program(device, INFO, "A", self.folder, segments, SETTINGS, lambda: True)
            self.assertEqual(device.events, [])

    def test_unique_backups(self):
        first = backup_board(Fake(), INFO, "A", self.folder)
        second = backup_board(Fake(), INFO, "A", self.folder)
        self.assertNotEqual(first, second)

    def test_boot_evidence_not_passthrough(self):
        self.assertIn("待", assess_boot(b""))
        self.assertIn("异常", assess_boot(b"Guru Meditation"))
        self.assertIn("异常", assess_boot(b"rst:0x1 rst:0x3"))
        self.assertIn("待接线", assess_boot(b"dual_s3_hid_proxy Calling app_main()"))


if __name__ == "__main__":
    unittest.main()
