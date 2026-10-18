"""配置边界与预览选择逻辑测试。"""
import tempfile
import unittest
from pathlib import Path
from profiles import list_profiles,save_profile,load_profile,profile_path
from output_control import nearest_head


class ProfileTests(unittest.TestCase):
    def test_dotted_name_stays_in_profiles_directory(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from profiles import profile_path
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(profile_path(root, "cf.onnx"), root / "cf.onnx.json")
            for name in ("../escape", "con.onnx", "cf.onnx."):
                with self.assertRaises(ValueError):
                    profile_path(root, name)

    def test_named_profiles(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            save_profile(folder,"游戏 A",{"classes":2})
            save_profile(folder,"游戏 B",{"classes":3})
            self.assertEqual(list_profiles(folder),["游戏 A","游戏 B"])
            self.assertEqual(load_profile(folder,"游戏 A")["classes"],2)

    def test_no_path_escape(self):
        for name in ("../outside","a\\b","CON","trailing.","", ".hidden"):
            with self.assertRaises(ValueError):
                profile_path(Path("profiles"),name)

    def test_preview_matches_nearest_head(self):
        boxes=[{"class":0,"box":[45,45,55,55]},
               {"class":1,"box":[70,45,90,55]},
               {"class":1,"box":[50,45,60,55]}]
        self.assertIs(nearest_head(boxes,100,100,50),boxes[2])
        self.assertIsNone(nearest_head(boxes,100,100,4))


if __name__=="__main__":
    unittest.main()
