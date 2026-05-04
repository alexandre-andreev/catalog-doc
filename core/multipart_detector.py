"""
Heuristic detection of multi-part books in the same directory.

Logic: files in the same directory are considered parts of one book when
they share a common name prefix and carry sequential part numbers — either
via an explicit keyword (часть/том/chapter/part/vol …) or a plain trailing
number separated by a space, dash, or underscore.

Returns a mapping {full_path: group_id} only for files that belong to a
detected group (two or more files with at least one consecutive number pair).

Filtering applied to reduce false positives:
- Only "book-like" formats are considered (plain-text .txt/.rtf excluded).
- Files smaller than MIN_SIZE_KB are ignored (code snippets, etc.).
"""

import re
from collections import defaultdict
from pathlib import Path

from .scanner import FileInfo

# Only formats that are typically standalone book volumes
_BOOK_EXTS = {'.pdf', '.epub', '.djvu', '.fb2', '.docx', '.doc', '.mobi', '.azw3'}

# Minimum file size to consider (filters out tiny code/data fragments)
_MIN_SIZE_KB = 50

# "Title часть 2", "Книга том 3", "Name, Part 4", "Title Vol.2"
_KW_END = re.compile(
    r'^(.+?)[\s_,\-]+'
    r'(?:часть|раздел|том|глава|кн(?:ига)?'
    r'|chapter|part|vol(?:ume)?|section|book|ch)'
    r'[\s_.\-]*(\d+)\s*$',
    re.IGNORECASE | re.UNICODE,
)

# "Title 2", "title_02", "some-name_3"  (1–2 digit suffix to avoid years)
_TRAIL_NUM = re.compile(
    r'^(.+?)[\s_\-]+(\d{1,2})\s*$',
    re.UNICODE,
)


def detect_multipart_groups(files: list[FileInfo]) -> dict[str, str]:
    """Return {full_path: group_id} for detected multi-part book files."""
    by_dir: dict[str, list[FileInfo]] = defaultdict(list)
    for f in files:
        ext = Path(f.name).suffix.lower()
        if ext in _BOOK_EXTS and f.size_bytes >= _MIN_SIZE_KB * 1024:
            by_dir[f.directory].append(f)

    result: dict[str, str] = {}
    counter = 0

    for dir_files in by_dir.values():
        if len(dir_files) < 2:
            continue

        parsed: list[tuple[str, int, FileInfo]] = []
        for f in dir_files:
            stem = Path(f.name).stem
            prefix, num = _parse_stem(stem)
            if prefix is not None:
                parsed.append((prefix.strip().lower(), num, f))

        if len(parsed) < 2:
            continue

        by_prefix: dict[str, list[tuple[int, FileInfo]]] = defaultdict(list)
        for prefix, num, f in parsed:
            by_prefix[prefix].append((num, f))

        for prefix, num_files in by_prefix.items():
            if len(num_files) < 2:
                continue
            nums = sorted({n for n, _ in num_files})
            if not _has_consecutive(nums):
                continue

            counter += 1
            gid = f"МТ-{counter:04d}"
            for _, f in num_files:
                result[f.full_path] = gid

    return result


def _parse_stem(stem: str) -> tuple[str | None, int]:
    m = _KW_END.match(stem)
    if m:
        return m.group(1), int(m.group(2))
    m = _TRAIL_NUM.match(stem)
    if m:
        return m.group(1), int(m.group(2))
    return None, 0


def _has_consecutive(nums: list[int]) -> bool:
    return any(nums[i + 1] - nums[i] == 1 for i in range(len(nums) - 1))
