"""
Unified AI provider with automatic failover.

Priority and keys are read from config.settings at call time so that
changes saved in the Settings tab take effect without restart.
"""

from config import settings as cfg


class AIProvider:
    def classify(self, filename: str, text: str) -> dict:
        """Classify a document with automatic provider failover."""
        primary = cfg.get("AI_PRIORITY", "gemini")
        providers = (
            [self._gemini_classify, self._groq_classify]
            if primary == "gemini"
            else [self._groq_classify, self._gemini_classify]
        )
        last_err: Exception | None = None
        for fn in providers:
            try:
                return fn(filename, text)
            except Exception as e:
                last_err = e
                continue
        return {
            "title": filename, "author": None, "year": None,
            "publisher": None, "category": "Прочее",
            "error": str(last_err),
        }

    def _gemini_classify(self, filename: str, text: str) -> dict:
        key = cfg.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY не задан")
        from ai.gemini_provider import GeminiProvider
        return GeminiProvider(key).classify(filename, text)

    def _groq_classify(self, filename: str, text: str) -> dict:
        key = cfg.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY не задан")
        from ai.groq_provider import GroqProvider
        return GroqProvider(key).classify(filename, text)
