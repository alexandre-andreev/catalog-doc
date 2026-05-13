import json
import re
import google.generativeai as genai

import ai.taxonomy as _tax
from ai.taxonomy import META_ONLY_PROMPT

# Try in order; fall back if a model returns 404 (not available in this region/tier)
_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]

_CLASSIFY_PROMPT = """\
Ты — библиотечный каталогизатор. Проанализируй документ и верни ТОЛЬКО JSON (без markdown, без пояснений).

Имя файла: {filename}
Фрагмент текста:
{text}

{category_guide}

Формат ответа (строго):
{{
  "title": "Название книги на языке оригинала",
  "author": "Автор или авторы через точку с запятой",
  "year": "Год издания или null",
  "publisher": "Издательство или null",
  "category": "Раздел/Подраздел"
}}
"""


class GeminiProvider:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)

    def test_connection(self) -> str:
        for model_name in _MODELS:
            try:
                model = genai.GenerativeModel(model_name)
                resp = model.generate_content("Reply with the word OK only.")
                _ = resp.text
                return "ok"
            except Exception as e:
                msg = str(e)
                if "404" in msg:
                    continue
                return _friendly_error(e)
        return f"Ни одна модель не доступна: {_MODELS}"

    def classify(self, filename: str, text: str, metadata_only: bool = False) -> dict:
        if metadata_only:
            prompt = META_ONLY_PROMPT.format(filename=filename, text=text[:1400])
        else:
            prompt = _CLASSIFY_PROMPT.format(
                filename=filename, text=text[:1400], category_guide=_tax.get_active()[1])

        for model_name in _MODELS:
            result = self._try_model(model_name, prompt, filename)
            if result is not None:
                return result
        raise RuntimeError(f"Gemini: ни одна модель не доступна ({', '.join(_MODELS)})")

    def classify_media(self, dirname: str, subdirs: list[str]) -> dict:
        from ai.taxonomy import MEDIA_CLASSIFY_PROMPT
        subdirs_str = ", ".join(subdirs[:10]) or "—"
        prompt = MEDIA_CLASSIFY_PROMPT.format(
            dirname=dirname, subdirs=subdirs_str, category_guide=_tax.get_active()[1])
        for model_name in _MODELS:
            try:
                model = genai.GenerativeModel(model_name)
                resp = model.generate_content(prompt)
                raw = _extract_json(resp.text)
                result = json.loads(raw)
                if not result.get("title"):
                    result["title"] = dirname
                if not str(result.get("category", "")).startswith("Медиа"):
                    result["category"] = "Медиа/Прочее"
                return result
            except json.JSONDecodeError:
                return {"title": dirname, "category": "Медиа/Прочее"}
            except Exception as e:
                if "404" in str(e):
                    continue
                return {"title": dirname, "category": "Медиа/Прочее"}
        return {"title": dirname, "category": "Медиа/Прочее"}

    def summarize(self, filename: str, text: str) -> str:
        from ai.taxonomy import SUMMARY_PROMPT
        prompt = SUMMARY_PROMPT.format(filename=filename, text=text[:6000])
        for model_name in _MODELS:
            try:
                model = genai.GenerativeModel(model_name)
                resp = model.generate_content(prompt)
                return resp.text.strip()
            except Exception as e:
                if "404" in str(e):
                    continue
                raise
        raise RuntimeError(f"Gemini: ни одна модель не доступна ({', '.join(_MODELS)})")

    def _try_model(self, model_name: str, prompt: str, filename: str) -> dict | None:
        model = genai.GenerativeModel(model_name)
        try:
            resp = model.generate_content(prompt)
            raw = _extract_json(resp.text)
            return json.loads(raw)
        except json.JSONDecodeError:
            return _fallback(filename)
        except Exception as e:
            msg = str(e)
            if "404" in msg:
                return None  # try next model
            # On 429/quota: raise immediately so AIProvider can failover to Groq/OpenAI
            raise


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
    if "API_KEY_INVALID" in msg or "invalid" in msg.lower():
        return "Неверный API-ключ"
    if "429" in msg or "quota" in msg.lower():
        return "Лимит запросов (429)"
    if "403" in msg:
        return "Доступ запрещён (403)"
    if "404" in msg:
        return f"Модели {_MODELS} не найдены (404)"
    return msg[:120]
