"""Copy one game's models and compatible profiles into the sibling viewer.

No import happens until the user runs a group's one-click-import.cmd.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
def find_viewer(root):
    """Resolve a bundled NONX folder first, or the older sibling layout."""
    for candidate in (root.parent, root.parent / "ndi-yolo-viewer"):
        if (candidate / "main.py").is_file() and (candidate / "detector.py").is_file():
            return candidate.resolve()
    raise RuntimeError("Viewer not found. Place NONX inside the viewer project.")


VIEWER = find_viewer(ROOT)
CATALOG = ROOT / "model-catalog.json"
MANIFESTS = VIEWER / ".nonx-imports"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inside(path, root):
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def safe_name(value, limit):
    result = re.sub(r"[^\w\u4e00-\u9fff .-]", "_", value, flags=re.UNICODE).strip(" .")
    return result[:limit].rstrip(" .") or "model"


def profile_name(item, group):
    suffix = hashlib.sha256(item["path"].encode("utf-8")).hexdigest()[:8]
    return f"NONX-{safe_name(group.name, 8)}-{safe_name(Path(item['path']).stem, 15)}-{suffix}.json"


def profile_data(item, model_rel):
    count = item["classes"]
    labels = item.get("labels") or {}
    head_candidates = [int(k) for k, v in labels.items() if any(t in v.lower() for t in ("head", "tou", "头"))]
    teammate_candidates = [int(k) for k, v in labels.items() if any(t in v.lower() for t in ("teammate", "duiyou", "队友"))]
    head = head_candidates[0] if head_candidates else 0
    friend = teammate_candidates[0] if teammate_candidates else -1
    if friend == head:
        friend = -1
    return {
        "model": model_rel.as_posix(), "provider": "CPUExecutionProvider",
        "layout": item["layout"], "classes": count, "confidence": 0.25,
        "allowed": [], "roi": None, "roi_size": None, "source": "",
        "red_only": False, "shift_hold": False,
        "output_parameters": {"press_ms": 50, "gap_ms": 100, "stale_ms": 200,
                              "gain": 0.05, "max_step": 4, "radius": 150,
                              "head_class": head, "teammate_class": friend},
    }


def choose_group(raw):
    group = (ROOT / raw).resolve()
    if not inside(group, ROOT) or group == ROOT or not group.is_dir():
        raise ValueError("Invalid group directory")
    return group


def plan(group):
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    if catalog.get("schema") != 1:
        raise ValueError("Unsupported catalog schema")
    group_rel = group.relative_to(ROOT)
    items = [item for item in catalog["models"] if Path(item["path"]).parent == group_rel]
    if not items:
        raise ValueError("No cataloged models in this game folder")
    records = []
    for item in items:
        source = ROOT / item["path"]
        if not inside(source, group) or source.parent.resolve() != group.resolve() or not source.is_file():
            raise ValueError(f"Missing or unsafe source: {item['path']}")
        if sha256(source) != item["sha256"]:
            raise ValueError(f"Model changed since inspection: {item['path']}; rerun inspect_models.py")
        model_rel = Path("models") / "NONX" / item["path"]
        target = VIEWER / model_rel
        compatible = item.get("layout") in ("v5", "v8", "xyxy", "yolox") and isinstance(item.get("classes"), int) and 1 <= item["classes"] <= 1000
        profile = VIEWER / "profiles" / profile_name(item, group_rel)
        records.append({"item": item, "source": source, "target": target,
                        "model_rel": model_rel, "profile": profile if compatible else None})
    return records


def manifest_path(group):
    key = hashlib.sha256(group.relative_to(ROOT).as_posix().encode("utf-8")).hexdigest()[:12]
    return MANIFESTS / f"{key}.json"


def write_new(path, content=None, source=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with path.open("xb") as target:
            created = True
            if source is not None:
                with source.open("rb") as original:
                    shutil.copyfileobj(original, target)
            else:
                target.write(content)
    except Exception:
        if created and path.is_file():
            path.unlink()
        raise


def import_group(group, dry_run):
    records = plan(group)
    manifest = manifest_path(group)
    if manifest.exists():
        raise ValueError("This folder already has an import manifest. Remove it first, or inspect the manifest.")
    owned = []
    for record in records:
        for target in (record["target"], record["profile"]):
            if target is not None and not inside(target, VIEWER):
                raise ValueError(f"Destination escapes viewer: {target}")
            if target is not None and target.exists():
                raise ValueError(f"Destination already exists; no overwrite: {target}")
    compatible = sum(r["profile"] is not None for r in records)
    print(f"Group: {group.relative_to(ROOT)} | models: {len(records)} | profiles: {compatible} | unsupported: {len(records)-compatible}")
    if dry_run:
        return
    if not VIEWER.is_dir() or not (VIEWER / "main.py").is_file() or not (VIEWER / "profiles").is_dir():
        raise ValueError(f"Viewer project not found: {VIEWER}")
    try:
        for record in records:
            target = record["target"]
            write_new(target, source=record["source"])
            owned.append({"path": target.relative_to(VIEWER).as_posix(), "sha256": sha256(target)})
            if owned[-1]["sha256"] != record["item"]["sha256"]:
                raise ValueError(f"Copied model verification failed: {target}")
            if record["profile"] is not None:
                target = record["profile"]
                payload = json.dumps(profile_data(record["item"], record["model_rel"]), ensure_ascii=False, indent=2).encode("utf-8")
                write_new(target, content=payload)
                owned.append({"path": target.relative_to(VIEWER).as_posix(), "sha256": sha256(target)})
        write_new(manifest, content=json.dumps({"schema": 1, "group": group.relative_to(ROOT).as_posix(),
                                               "owned": owned}, ensure_ascii=False, indent=2).encode("utf-8"))
    except Exception:
        for entry in reversed(owned):
            target = VIEWER / entry["path"]
            if target.is_file() and sha256(target) == entry["sha256"]:
                target.unlink()
        raise
    print(f"Imported. Manifest: {manifest}")


def remove_group(group, dry_run):
    manifest = manifest_path(group)
    if not manifest.is_file():
        raise ValueError("No import manifest for this game folder")
    state = json.loads(manifest.read_text(encoding="utf-8"))
    if state.get("schema") != 1 or state.get("group") != group.relative_to(ROOT).as_posix():
        raise ValueError("Manifest does not match the selected folder")
    owned = state["owned"]
    for entry in owned:
        target = VIEWER / entry["path"]
        allowed_model = inside(target, VIEWER / "models" / "NONX" / state["group"])
        allowed_profile = target.parent.resolve() == (VIEWER / "profiles").resolve() and target.name.startswith("NONX-") and target.suffix == ".json"
        if not (allowed_model or allowed_profile):
            raise ValueError(f"Manifest refers to an unmanaged path: {target}")
        if not inside(target, VIEWER) or not target.is_file() or sha256(target) != entry["sha256"]:
            raise ValueError(f"A managed file changed or is missing. No files removed: {target}")
    print(f"Group: {group.relative_to(ROOT)} | managed files: {len(owned)}")
    if dry_run:
        return
    for entry in reversed(owned):
        (VIEWER / entry["path"]).unlink()
    manifest.unlink()
    for parent in sorted({(VIEWER / e["path"]).parent for e in owned}, key=lambda p: len(p.parts), reverse=True):
        while parent not in (VIEWER, VIEWER / "profiles", VIEWER / "models") and inside(parent, VIEWER):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    print("Removed only files created by this import.")


def main():
    parser = argparse.ArgumentParser(description="Import or undo one NONX game folder")
    parser.add_argument("action", choices=("import", "remove"))
    parser.add_argument("--group", required=True, help="game folder relative to NONX")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        group = choose_group(args.group)
        (import_group if args.action == "import" else remove_group)(group, args.dry_run)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
