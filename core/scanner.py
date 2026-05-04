import os
import hashlib
import threading
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

SUPPORTED_EXTENSIONS = {
    '.pdf', '.epub', '.djvu', '.fb2', '.docx', '.doc',
    '.txt', '.rtf', '.mobi', '.azw3'
}


@dataclass
class FileInfo:
    name: str
    directory: str
    size_bytes: int
    modified: datetime
    sha256: str = ""
    group_id: str | None = None   # set by multipart_detector after scan

    @property
    def size_mb(self) -> float:
        return round(self.size_bytes / (1024 * 1024), 2)

    @property
    def extension(self) -> str:
        return Path(self.name).suffix.upper().lstrip('.')

    @property
    def full_path(self) -> str:
        return os.path.join(self.directory, self.name)


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
