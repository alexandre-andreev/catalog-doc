from dataclasses import dataclass, field
from collections import defaultdict

from core.scanner import FileInfo


@dataclass
class DupGroup:
    sha256: str          # empty string when detected by name+size fallback
    files: list[FileInfo] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.files)

    @property
    def size_mb(self) -> float:
        return self.files[0].size_mb if self.files else 0.0

    @property
    def wasted_mb(self) -> float:
        return (self.count - 1) * self.size_mb


def find_duplicates(files: list[FileInfo]) -> list[DupGroup]:
    """Exact duplicates by SHA-256. Files are sorted newest-first within each group."""
    by_hash: dict[str, list[FileInfo]] = defaultdict(list)
    for f in files:
        if f.sha256:
            by_hash[f.sha256].append(f)
    groups = [
        DupGroup(sha256=sha,
                 files=sorted(flist, key=lambda f: f.modified, reverse=True))
        for sha, flist in by_hash.items()
        if len(flist) >= 2
    ]
    groups.sort(key=lambda g: g.wasted_mb, reverse=True)
    return groups


def find_by_name_size(files: list[FileInfo]) -> list[DupGroup]:
    """Fallback: group by (lowercase name, size_bytes) when SHA-256 is unavailable."""
    by_key: dict[tuple, list[FileInfo]] = defaultdict(list)
    for f in files:
        key = (f.name.lower(), f.size_bytes)
        by_key[key].append(f)
    groups = [
        DupGroup(sha256="",
                 files=sorted(flist, key=lambda f: f.modified, reverse=True))
        for flist in by_key.values()
        if len(flist) >= 2
    ]
    groups.sort(key=lambda g: g.wasted_mb, reverse=True)
    return groups
