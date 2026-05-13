import threading
from typing import Callable
from core.scanner import FileInfo, MediaDirInfo
from ai.provider import AIProvider
from utils import text_extractor
from utils import cache as cache_utils


class Classifier:
    def __init__(self):
        self._provider = AIProvider()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    @property
    def is_stopped(self) -> bool:
        return self._stop.is_set()

    def classify_all(
        self,
        files: list[FileInfo | MediaDirInfo],
        cache: dict,
        on_result: Callable[[int, FileInfo | MediaDirInfo, dict, bool], None],
        on_progress: Callable[[int, int], None],
        on_done: Callable[[dict], None],
        on_error: Callable[[str, str], None] | None = None,
        metadata_only: bool = False,
    ):
        self._stop.clear()
        total = len(files)

        for i, info in enumerate(files):
            if self._stop.is_set():
                break

            on_progress(i, total)

            # ── Media directory: classify by folder name (no text extraction) ──
            if info.is_media_dir:
                cached = cache_utils.get_cached(info, cache)
                if cached is not None and "error" not in cached and cached.get("category"):
                    on_result(i, info, cached, True)
                    continue
                try:
                    result = self._provider.classify_media(info.name, info.subdirs)
                    if not result.get("title"):
                        result["title"] = info.name
                except Exception as e:
                    result = {"title": info.name, "category": "Медиа/Прочее",
                              "error": str(e)[:120]}
                    if on_error:
                        on_error(info.full_path, str(e))
                cache_utils.set_cached(info, result, cache)
                cache_utils.save(cache)
                on_result(i, info, result, False)
                self._stop.wait(timeout=self._provider.call_delay)
                continue

            # ── Regular file ──────────────────────────────────────────────────
            cached = cache_utils.get_cached(info, cache)

            # Use cached result if it is "good" for the current mode:
            #   - no error field
            #   - metadata_only mode: don't care about category
            #   - full mode: need a category too
            if cached is not None and "error" not in cached:
                if metadata_only or cached.get("category"):
                    on_result(i, info, cached, True)
                    continue

            # Previous good entry (no error) to fall back on if the new attempt fails
            prev_good = cached if (cached and "error" not in cached) else None

            ex = text_extractor.extract(info.full_path)

            parts = []
            if ex.title:
                parts.append(f"Заголовок: {ex.title}")
            if ex.author:
                parts.append(f"Автор: {ex.author}")
            if ex.year:
                parts.append(f"Год: {ex.year}")
            if ex.description:
                parts.append(f"Описание: {ex.description[:1500]}")
            if ex.text:
                parts.append(ex.text[:2000])
            combined = "\n".join(parts)

            try:
                # Pass the full path so AI can use folder hierarchy as context
                result = self._provider.classify(info.full_path, combined, metadata_only)
                # Back-fill blanks from file metadata
                for fld, val in (("title", ex.title), ("author", ex.author),
                                  ("year", ex.year), ("publisher", ex.publisher)):
                    if val and not result.get(fld):
                        result[fld] = val
                # If title still empty, derive from filename (strip extension, fix underscores)
                if not result.get("title"):
                    result["title"] = _filename_to_title(info.name)
                if metadata_only:
                    result.pop("category", None)
            except Exception as e:
                # Build error result: prefer metadata from previous good cache entry,
                # then freshly extracted text, then fall back to filename
                pg = prev_good or {}
                result = {
                    "title":     pg.get("title")     or ex.title     or _filename_to_title(info.name),
                    "author":    pg.get("author")     or ex.author    or None,
                    "year":      pg.get("year")       or ex.year      or None,
                    "publisher": pg.get("publisher")  or ex.publisher or None,
                    "category":  pg.get("category")   or "Прочее",
                    "error":     str(e)[:120],
                }
                if on_error:
                    on_error(info.full_path, str(e))

            cache_utils.set_cached(info, result, cache)
            cache_utils.save(cache)
            on_result(i, info, result, False)

            self._stop.wait(timeout=self._provider.call_delay)

        on_progress(total, total)
        on_done(cache)


def _filename_to_title(filename: str) -> str:
    from pathlib import Path
    stem = Path(filename).stem
    return stem.replace("_", " ").replace("-", " ").strip()
