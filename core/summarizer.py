import threading
from typing import Callable

from core.scanner import FileInfo
from ai.provider import AIProvider
from utils import text_extractor
from utils import cache as cache_utils


class Summarizer:
    def __init__(self):
        self._provider = AIProvider()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    @property
    def is_stopped(self) -> bool:
        return self._stop.is_set()

    def summarize_all(
        self,
        files: list[FileInfo],
        cache: dict,
        on_result: Callable[[int, FileInfo, str, bool], None],
        on_progress: Callable[[int, int], None],
        on_done: Callable[[dict], None],
        on_error: Callable[[str, str], None] | None = None,
    ):
        self._stop.clear()
        total = len(files)

        for i, info in enumerate(files):
            if self._stop.is_set():
                break

            on_progress(i, total)

            cached = cache_utils.get_summary(info, cache)
            if cached is not None:
                on_result(i, info, cached, True)
                continue

            ex = text_extractor.extract_deep(info.full_path)
            parts = []
            if ex.title:
                parts.append(f"Заголовок: {ex.title}")
            if ex.author:
                parts.append(f"Автор: {ex.author}")
            if ex.description:
                parts.append(f"Аннотация: {ex.description[:500]}")
            if ex.text:
                parts.append(ex.text)
            combined = "\n".join(parts)

            try:
                summary = self._provider.summarize(info.full_path, combined)
            except Exception as e:
                summary = f"Ошибка: {str(e)[:100]}"
                if on_error:
                    on_error(info.full_path, str(e))

            cache_utils.set_summary(info, summary, cache)
            cache_utils.save_summaries(cache)
            on_result(i, info, summary, False)

            self._stop.wait(timeout=self._provider.call_delay)

        on_progress(total, total)
        on_done(cache)
