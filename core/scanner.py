import os
import hashlib
import threading
from collections import defaultdict
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

SUPPORTED_EXTENSIONS = {
    '.pdf', '.epub', '.djvu', '.fb2', '.docx', '.doc',
    '.txt', '.rtf', '.mobi', '.azw3', '.zip'
}

MEDIA_EXTENSIONS = {
    '.mp3', '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv',
    '.wav', '.flac', '.m4a', '.m4v', '.webm', '.ogg',
    '.aac', '.wma', '.opus', '.ts', '.vob', '.mpg', '.mpeg', '.m2ts',
}


@dataclass
class FileInfo:
    name: str
    directory: str
    size_bytes: int
    modified: datetime
    sha256: str = ""
    group_id: str | None = None   # set by multipart_detector after scan

    is_media_dir: bool = False    # sentinel — always False for regular files

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / (1024 * 1024), 2)

    @property
    def extension(self) -> str:
        return Path(self.name).suffix.upper().lstrip('.')

    @property
    def full_path(self) -> str:
        return os.path.join(self.directory, self.name)


@dataclass
class MediaDirInfo:
    """A directory that contains media files — treated as a single catalog item."""
    name: str           # directory name
    directory: str      # parent directory path
    size_bytes: int     # total size of all contents (recursive)
    media_count: int    # total number of media files (recursive)
    subdirs: list[str]  # immediate subdirectory names (for AI context)
    modified: datetime = field(default_factory=datetime.now)
    sha256: str = ""
    group_id: str | None = None
    is_media_dir: bool = True

    @property
    def full_path(self) -> str:
        return os.path.join(self.directory, self.name)

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / (1024 * 1024), 2)

    @property
    def extension(self) -> str:
        return "МЕДИА"


class Scanner:
    def __init__(self):
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    @property
    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def scan(
        self,
        root_dir: str,
        on_progress: Optional[Callable[[int, int, str], None]] = None,
        on_file_found: Optional[Callable[['FileInfo'], None]] = None,
        on_done: Optional[Callable[[list['FileInfo']], None]] = None,
        on_error: Optional[Callable[[str, str], None]] = None,
        compute_hashes: bool = True,
    ) -> list['FileInfo']:
        self._stop_event.clear()
        results: list[FileInfo] = []

        # Pass 1: collect all matching paths (fast)
        all_files: list[str] = []
        for dirpath, _, filenames in os.walk(root_dir):
            if self._stop_event.is_set():
                break
            for filename in filenames:
                if Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS:
                    all_files.append(os.path.join(dirpath, filename))

        total = len(all_files)

        # Pass 2: stat + hash each file
        for i, filepath in enumerate(all_files):
            if self._stop_event.is_set():
                break
            try:
                stat = os.stat(filepath)
                sha256 = self._compute_sha256(filepath) if compute_hashes else ""
                info = FileInfo(
                    name=os.path.basename(filepath),
                    directory=os.path.dirname(filepath),
                    size_bytes=stat.st_size,
                    modified=datetime.fromtimestamp(stat.st_mtime),
                    sha256=sha256,
                )
                results.append(info)
                if on_file_found:
                    on_file_found(info)
                if on_progress:
                    on_progress(i + 1, total, filepath)
            except (PermissionError, OSError) as e:
                if on_error:
                    on_error(filepath, str(e))

        if on_done:
            on_done(results)

        return results

    def scan_media_dirs(
        self,
        root_dir: str,
        on_found: Optional[Callable[['MediaDirInfo'], None]] = None,
        on_done: Optional[Callable[[list['MediaDirInfo']], None]] = None,
    ) -> list['MediaDirInfo']:
        """Detect directories that contain media files; treat each as one catalog item.

        Only the top-most media-containing directory is reported: if a parent dir
        also has media files, the parent is reported and its children are not.
        """
        dir_media_count: dict[str, int] = {}      # dirs with ≥1 media file directly
        dir_file_size: dict[str, int] = defaultdict(int)
        dir_subdirs: dict[str, list[str]] = {}
        dir_mtime: dict[str, float] = {}

        for dirpath, subdirs, filenames in os.walk(root_dir):
            if self._stop_event.is_set():
                break
            dir_subdirs[dirpath] = subdirs[:]
            try:
                dir_mtime[dirpath] = os.path.getmtime(dirpath)
            except OSError:
                dir_mtime[dirpath] = 0.0

            media_in_dir = 0
            for fname in filenames:
                if Path(fname).suffix.lower() in MEDIA_EXTENSIONS:
                    media_in_dir += 1
                try:
                    dir_file_size[dirpath] += os.path.getsize(
                        os.path.join(dirpath, fname))
                except OSError:
                    pass

            if media_in_dir:
                dir_media_count[dirpath] = media_in_dir

        media_dirs_set = set(dir_media_count.keys())
        results: list[MediaDirInfo] = []

        for d in sorted(media_dirs_set):
            if d == root_dir:
                continue

            # Skip if any ancestor between d and root_dir is also a media dir
            has_media_ancestor = False
            p = str(Path(d).parent)
            while p != root_dir:
                if p in media_dirs_set:
                    has_media_ancestor = True
                    break
                parent = str(Path(p).parent)
                if parent == p:   # filesystem root
                    break
                p = parent

            if has_media_ancestor:
                continue

            # Sum sizes and media counts over d + all descendants
            prefix = d + os.sep
            total_bytes = sum(
                sz for path, sz in dir_file_size.items()
                if path == d or path.startswith(prefix)
            )
            total_media = sum(
                cnt for path, cnt in dir_media_count.items()
                if path == d or path.startswith(prefix)
            )
            subdirs = dir_subdirs.get(d, [])[:12]
            mtime = dir_mtime.get(d, 0.0)

            info = MediaDirInfo(
                name=os.path.basename(d),
                directory=os.path.dirname(d),
                size_bytes=total_bytes,
                media_count=total_media,
                subdirs=subdirs,
                modified=datetime.fromtimestamp(mtime) if mtime else datetime.now(),
            )
            results.append(info)
            if on_found:
                on_found(info)

        if on_done:
            on_done(results)
        return results

    def _compute_sha256(self, filepath: str) -> str:
        h = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                while chunk := f.read(65536):
                    if self._stop_event.is_set():
                        return ""
                    h.update(chunk)
            return h.hexdigest()
        except (PermissionError, OSError):
            return ""
