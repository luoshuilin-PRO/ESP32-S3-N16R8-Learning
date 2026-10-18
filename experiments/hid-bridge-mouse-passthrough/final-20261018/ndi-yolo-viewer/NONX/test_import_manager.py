import hashlib
import json
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

import import_manager as manager


class ImportRoundTripTest(unittest.TestCase):
    def test_bundled_project_copy_and_undo(self):
        with tempfile.TemporaryDirectory() as temp:
            viewer = Path(temp) / "original"
            root = viewer / "NONX"
            game = root / "game"
            game.mkdir(parents=True)
            (viewer / "profiles").mkdir()
            for name in ("main.py", "detector.py"):
                (viewer / name).write_text("", encoding="utf-8")
            (game / "sample.onnx").write_bytes(b"test")
            catalog = root / "model-catalog.json"
            catalog.write_text(json.dumps({"schema": 1, "models": [{
                "path": "game/sample.onnx", "sha256": hashlib.sha256(b"test").hexdigest(),
                "classes": 1, "layout": "v8"}]}), encoding="utf-8")
            self.assertEqual(manager.find_viewer(root), viewer.resolve())
            with patch.multiple(manager, ROOT=root, VIEWER=viewer, CATALOG=catalog,
                                MANIFESTS=viewer / ".nonx-imports"):
                manager.import_group(game, False)
            copied = Path(temp) / "new computer renamed project"
            shutil.copytree(viewer, copied)
            copied_root = copied / "NONX"
            self.assertEqual(manager.find_viewer(copied_root), copied.resolve())
            with patch.multiple(manager, ROOT=copied_root, VIEWER=copied,
                                CATALOG=copied_root / "model-catalog.json",
                                MANIFESTS=copied / ".nonx-imports"):
                manager.remove_group(copied_root / "game", False)
            self.assertFalse((copied / "models" / "NONX" / "game" / "sample.onnx").exists())
            self.assertTrue((viewer / "models" / "NONX" / "game" / "sample.onnx").exists())

    def test_existing_file_not_removed_on_create_collision(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "existing.txt"
            path.write_bytes(b"original")
            with self.assertRaises(FileExistsError):
                manager.write_new(path, content=b"replacement")
            self.assertEqual(path.read_bytes(), b"original")

    def test_import_remove_preserves_changed_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "NONX"
            viewer = Path(temp) / "ndi-yolo-viewer"
            game = root / "game"
            game.mkdir(parents=True)
            (viewer / "profiles").mkdir(parents=True)
            (viewer / "main.py").write_text("", encoding="utf-8")
            source = game / "sample.onnx"
            source.write_bytes(b"sample model bytes")
            catalog = root / "model-catalog.json"
            catalog.write_text(json.dumps({"schema": 1, "models": [{
                "path": "game/sample.onnx", "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "classes": 2, "layout": "v8", "labels": {"0": "head", "1": "teammate"}
            }]}), encoding="utf-8")
            with patch.multiple(manager, ROOT=root, VIEWER=viewer, CATALOG=catalog,
                                MANIFESTS=viewer / ".nonx-imports"):
                manager.import_group(game, False)
                model = viewer / "models" / "NONX" / "game" / "sample.onnx"
                self.assertEqual(model.read_bytes(), source.read_bytes())
                profiles = list((viewer / "profiles").glob("NONX-*.json"))
                self.assertEqual(len(profiles), 1)
                data = json.loads(profiles[0].read_text(encoding="utf-8"))
                self.assertEqual(data["output_parameters"]["head_class"], 0)
                self.assertFalse(data["red_only"])
                manifest = manager.manifest_path(game)
                original_manifest = manifest.read_text(encoding="utf-8")
                unrelated = viewer / "config.json"
                unrelated.write_bytes(b"keep")
                altered = json.loads(original_manifest)
                altered["owned"].append({"path": "config.json", "sha256": manager.sha256(unrelated)})
                manifest.write_text(json.dumps(altered), encoding="utf-8")
                with self.assertRaises(ValueError):
                    manager.remove_group(game, False)
                self.assertEqual(unrelated.read_bytes(), b"keep")
                manifest.write_text(original_manifest, encoding="utf-8")
                model.write_bytes(b"changed by user")
                with self.assertRaises(ValueError):
                    manager.remove_group(game, False)
                self.assertTrue(profiles[0].exists())
                model.write_bytes(source.read_bytes())
                manager.remove_group(game, False)
                self.assertFalse(model.exists())
                self.assertFalse(profiles[0].exists())


if __name__ == "__main__":
    unittest.main()
