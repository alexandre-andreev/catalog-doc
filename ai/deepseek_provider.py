import json
import re
from openai import OpenAI

import ai.taxonomy as _tax
from ai.taxonomy import META_ONLY_PROMPT

# deepseek-chat is their flagship model (~$0.14/1M input tokens, very cheap)
_MODEL = "deepseek-chat"
_BASE_URL = "https://api.deepseek.com"

_CLASSIFY_PROMPT = """\
Ты — библиотечный каталогизатор. Верни ТОЛЬКО JSON без markdown.

Файл: {filename}
Текст: {text}

{category_guide}

Формат:
{{"title": "Название на языке оригинала", "author": "Автор(ы) через ';'", "year": "Год или null", "publisher": "Издательство или null", "category": "Раздел/Подраздел"}}
"""


class DeepSeekProvider:
    def __init__(self, api_key: str):
        self._client = OpenAI(api_key=api_key, base_url=_BASE_URL)

    def test_connection(self) -> str:
        try:
            resp = self._client.chat.completions.create(
                model=_MODEL,
                messages=[{"role": "user", "content": "Reply with OK only."}],
                max_tokens=5,
                temperature=0,
            )
            _ = resp.choices[0].message.content
            return "ok"
        except Exception as e:
            return _friendly_error(e)

    def classify(self, filename: str, text: str, metadata_only: bool = False) -> dict:
        if metadata_only:
            prompt = META_ONLY_PROMPT.format(filename=filename, text=text[:1400])
        else:
            prompt = _CLASSIFY_PROMPT.format(
                filename=filename, text=text[:1400], category_guide=_tax.get_active()[1])
        try:
            resp = self._client.chat.completions.create(
                model=_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300,
            )
            raw = _extract_json(resp.choices[0].message.content)
            return json.loads(raw)
        except json.JSONDecodeError:
            return _fallback(filename)


    def classify_media(self, dirname: str, subdirs: list[str]) -> dict:
        from ai.taxonomy import MEDIA_CLASSIFY_PROMPT
        subdirs_str = ", ".join(subdirs[:10]) or "—"
        prompt = MEDIA_CLASSIFY_PROMPT.format(
            dirname=dirname, subdirs=subdirs_str, category_guide=_tax.get_active()[1])
        try:
            resp = self._client.chat.completions.create(
                model=_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1, max_tokens=150,
            )
            raw = _extract_json(resp.choices[0].message.content)
            result = json.loads(raw)
            if not result.get("title"):
                result["title"] = dirname
            if not str(result.get("category", "")).startswith("Медиа"):
                result["category"] = "Медиа/Прочее"
            return result
        except Exception:
            return {"title": dirname, "category": "Медиа/Прочее"}

    def summarize(self, filename: str, text: str) -> str:
        from ai.taxonomy import SUMMARY_PROMPT
        prompt = SUMMARY_PROMPT.format(filename=filename, text=text[:6000])
        resp = self._client.chat.completions.create(
            model=_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        )
        return resp.choices[0].message.content.strip()


def _extract_json(text: str) -> str:
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    return m.group() if m else text


def _fallback(filename: str) -> dict:
    return {"title": filename, "author": None, "year": None,
            "publisher": None, "category": "Прочее"}


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    if "invalid_api_key" in msg or "Authentication" in msg or "401" in msg:
        return "Неверный API-ключ"
    if "429" in msg or "rate" in msg.lower():
        return "Лимит запросов (429)"
    if "402" in msg or "insufficient" in msg.lower() or "balance" in msg.lower():
        return "Недостаточно средств на балансе"
    return msg[:120]
