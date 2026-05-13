import json
import hashlib
from datetime import datetime
from pathlib import Path
from core.scanner import FileInfo

CACHE_FILE = Path("cache/classifications.json")
FILE_LIST_FILE = Path("cache/file_list.json")
SUMMARY_FILE = Path("cache/summaries.json")


def _key(info) -> str:
    if getattr(info, "is_media_dir", False):
        return f"mediadir:{hashlib.md5(info.full_path.encode('utf-8')).hexdigest()}"
    if info.sha256:
        return f"sha256:{info.sha256}"
    return f"path:{hashlib.md5(info.full_path.encode('utf-8')).hexdigest()}"


# ---------------------------------------------------------------- classifications

def load() -> dict:
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save(cache: dict):
    CACHE_FILE.parent.mkdir(exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_cached(info: FileInfo, cache: dict) -> dict | None:
    return cache.get(_key(info))


def set_cached(info: FileInfo, result: dict, cache: dict):
    cache[_key(info)] = result


# ---------------------------------------------------------------- summaries

def load_summaries() -> dict:
    if SUMMARY_FILE.exists():
        try:
            with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_summaries(cache: dict):
    SUMMARY_FILE.parent.mkdir(exist_ok=True)
    with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def get_summary(info: FileInfo, cache: dict) -> str | None:
    entry = cache.get(_key(info))
    return entry.get("summary") if entry else None


def set_summary(info: FileInfo, summary: str, cache: dict):
    cache[_key(info)] = {"summary": summary, "at": datetime.now().isoformat()}


# ---------------------------------------------------------------- file list

def save_file_list(files: list[FileInfo], root_dir: str = ""):
    data = {
        "saved_at": datetime.now().isoformat(),
        "root_dir": root_dir,
        "files": [
            {
                "name": f.name,
                "directory": f.directory,
                "size_bytes": f.size_bytes,
                "modified": f.modified.isoformat(),
                "sha256": f.sha256,
                "group_id": f.group_id,
            }
            for f in files
        ],
    }
    FILE_LIST_FILE.parent.mkdir(exist_ok=True)
    with open(FILE_LIST_FILE, "w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)


def load_file_list() -> tuple[list[FileInfo], str, str] | tuple[None, None, None]:
    """Returns (files, saved_at_str, root_dir) or (None, None, None) if not found."""
    if not FILE_LIST_FILE.exists():
        return None, None, None
    try:
        with open(FILE_LIST_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        files = [
            FileInfo(
                name=d["name"],
                directory=d["directory"],
                size_bytes=d["size_bytes"],
                modified=datetime.fromisoformat(d["modified"]),
                sha256=d.get("sha256", ""),
                group_id=d.get("group_id"),
            )
            for d in data["files"]
        ]
        saved_at = data.get("saved_at", "")
        root_dir = data.get("root_dir", "")
        return files, saved_at, root_dir
    except Exception:
        return None, None, None
