"""
Unified AI provider with automatic failover.

Priority and keys are read from config.settings at call time so that
changes saved in the Settings tab take effect without restart.
"""

from config import settings as cfg

# Delays between calls (seconds) tuned to free-tier rate limits
# DeepSeek: 60 RPM free tier → 1.0s
# OpenAI gpt-4o-mini: 500 RPM → 0.5s
# Groq llama-3.3-70b: 30 RPM / 14400 TPM → 3.8s
# Gemini 2.5-flash-lite: 15 RPM → 4.2s
_DELAYS = {"deepseek": 1.0, "openai": 0.5, "groq": 3.8, "gemini": 4.2}

_PROVIDER_ORDER = {
    "deepseek": ["deepseek", "groq", "gemini"],
    "openai":   ["openai", "groq", "gemini"],
    "groq":     ["groq", "deepseek", "gemini"],
    "gemini":   ["gemini", "groq", "deepseek"],
}


class AIProvider:
    @property
    def call_delay(self) -> float:
        primary = cfg.get("AI_PRIORITY", "gemini")
        return _DELAYS.get(primary, 3.8)

    def classify(self, filename: str, text: str, metadata_only: bool = False) -> dict:
        primary = cfg.get("AI_PRIORITY", "gemini")
        order = _PROVIDER_ORDER.get(primary, _PROVIDER_ORDER["gemini"])

        last_err: Exception | None = None
        for name in order:
            try:
                return self._call(name, filename, text, metadata_only)
            except Exception as e:
                last_err = e
                continue

        return {
            "title": filename, "author": None, "year": None,
            "publisher": None, "category": "Прочее",
            "error": str(last_err),
        }

    def classify_media(self, dirname: str, subdirs: list[str]) -> dict:
        primary = cfg.get("AI_PRIORITY", "gemini")
        order = _PROVIDER_ORDER.get(primary, _PROVIDER_ORDER["gemini"])
        last_err: Exception | None = None
        for name in order:
            try:
                return self._call_media(name, dirname, subdirs)
            except Exception as e:
                last_err = e
                continue
        return {"title": dirname, "category": "Медиа/Прочее", "error": str(last_err)}

    def summarize(self, filename: str, text: str) -> str:
        primary = cfg.get("AI_PRIORITY", "gemini")
        order = _PROVIDER_ORDER.get(primary, _PROVIDER_ORDER["gemini"])
        last_err: Exception | None = None
        for name in order:
            try:
                return self._call_summarize(name, filename, text)
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(str(last_err))

    def _call_summarize(self, name: str, filename: str, text: str) -> str:
        if name == "deepseek":
            key = cfg.get("DEEPSEEK_API_KEY")
            if not key:
                raise RuntimeError("DEEPSEEK_API_KEY не задан")
            from ai.deepseek_provider import DeepSeekProvider
            return DeepSeekProvider(key).summarize(filename, text)
        if name == "openai":
            key = cfg.get("GPT_API_KEY")
            if not key:
                raise RuntimeError("GPT_API_KEY не задан")
            from ai.openai_provider import OpenAIProvider
            return OpenAIProvider(key).summarize(filename, text)
        if name == "groq":
            key = cfg.get("GROQ_API_KEY")
            if not key:
                raise RuntimeError("GROQ_API_KEY не задан")
            from ai.groq_provider import GroqProvider
            return GroqProvider(key).summarize(filename, text)
        key = cfg.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY не задан")
        from ai.gemini_provider import GeminiProvider
        return GeminiProvider(key).summarize(filename, text)

    def _call_media(self, name: str, dirname: str, subdirs: list[str]) -> dict:
        if name == "deepseek":
            key = cfg.get("DEEPSEEK_API_KEY")
            if not key:
                raise RuntimeError("DEEPSEEK_API_KEY не задан")
            from ai.deepseek_provider import DeepSeekProvider
            return DeepSeekProvider(key).classify_media(dirname, subdirs)
        if name == "openai":
            key = cfg.get("GPT_API_KEY")
            if not key:
                raise RuntimeError("GPT_API_KEY не задан")
            from ai.openai_provider import OpenAIProvider
            return OpenAIProvider(key).classify_media(dirname, subdirs)
        if name == "groq":
            key = cfg.get("GROQ_API_KEY")
            if not key:
                raise RuntimeError("GROQ_API_KEY не задан")
            from ai.groq_provider import GroqProvider
            return GroqProvider(key).classify_media(dirname, subdirs)
        key = cfg.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY не задан")
        from ai.gemini_provider import GeminiProvider
        return GeminiProvider(key).classify_media(dirname, subdirs)

    def _call(self, name: str, filename: str, text: str, metadata_only: bool) -> dict:
        if name == "deepseek":
            key = cfg.get("DEEPSEEK_API_KEY")
            if not key:
                raise RuntimeError("DEEPSEEK_API_KEY не задан")
            from ai.deepseek_provider import DeepSeekProvider
            return DeepSeekProvider(key).classify(filename, text, metadata_only)
        if name == "openai":
            key = cfg.get("GPT_API_KEY")
            if not key:
                raise RuntimeError("GPT_API_KEY не задан")
            from ai.openai_provider import OpenAIProvider
            return OpenAIProvider(key).classify(filename, text, metadata_only)
        if name == "groq":
            key = cfg.get("GROQ_API_KEY")
            if not key:
                raise RuntimeError("GROQ_API_KEY не задан")
            from ai.groq_provider import GroqProvider
            return GroqProvider(key).classify(filename, text, metadata_only)
        # gemini
        key = cfg.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY не задан")
        from ai.gemini_provider import GeminiProvider
        return GeminiProvider(key).classify(filename, text, metadata_only)
