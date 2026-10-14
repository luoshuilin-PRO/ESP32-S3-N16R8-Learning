"""本地游戏配置文件；名称不作为任意文件路径使用。"""
import json
import re
from pathlib import Path


NAME = re.compile(r"[\w\u4e00-\u9fff][\w\u4e00-\u9fff -]{0,39}\Z", re.UNICODE)


def profile_path(directory, name):
    """输入目录和显示名称；返回限定在该目录中的 JSON 路径。"""
    name = name.strip()
    if not NAME.fullmatch(name) or name[-1] in " .":
        raise ValueError("配置名称请使用 1～40 个中文、字母、数字、空格、- 或 _")
    if name.casefold() in {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}:
        raise ValueError("配置名称与 Windows 保留名称冲突")
    return Path(directory) / f"{name}.json"


def list_profiles(directory):
    """输出有效的配置名称，不读取或执行配置内容。"""
    root = Path(directory)
    if not root.is_dir():
        return []
    names = []
    for path in root.glob("*.json"):
        try:
            if path.is_file() and profile_path(root, path.stem) == path:
                names.append(path.stem)
        except ValueError:
            continue
    return sorted(names)


def save_profile(directory, name, data):
    """保存一份配置，返回目标路径；文件仅包含 JSON。"""
    path = profile_path(directory, name)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_profile(directory, name):
    """读取配置并验证顶层为对象。"""
    data = json.loads(profile_path(directory, name).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("配置格式应为 JSON 对象")
    return data
