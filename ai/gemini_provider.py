import json
import time
import google.generativeai as genai

MODEL = "gemini-2.5-flash"

_CLASSIFY_PROMPT = """\
Ты — библиотечный каталогизатор. Проанализируй документ и верни ТОЛЬКО JSON (без markdown, без пояснений).

Имя файла: {filename}
Фрагмент текста:
{text}

Формат ответа (строго):
{{
  "title": "Название книги на языке оригинала",
  "author": "Автор или авторы через точку с запятой",
  "year": "Год издания или null",
  "publisher": "Издательство или null",
  "category": "Программирование/Python | Программирование/Web | Базы данных | Системное администрирование | Математика | Машинное обучение | Управление проектами | Художественная литература | Прочее"
}}
"""


class GeminiProvider:
    def __init__(self, api_key: str):
        self._key = api_key
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(MODEL)

    def test_connection(self) -> str:
        """Returns 'ok' or error description."""
        try:
            resp = self._model.generate_content("Reply with the word OK only.")
            _ = resp.text
            return "ok"
        except Exception as e:
            return _friendly_error(e)

    def classify(self, filename: str, text: str) -> dict:
        prompt = _CLASSIFY_PROMPT.format(filename=filename, text=text[:1500])
        for attempt in range(3):
            try:
                resp = self._model.generate_content(prompt)
                raw = resp.text.strip().removeprefix("```json").removesuffix("```").strip()
                return json.loads(raw)
            except json.JSONDecodeError:
                return _fallback(filename)
            except Exception as e:
                msg = str(e)
                if "429" in msg or "quota" in msg.lower() or "rate" in msg.lower():
                    wait = 60 * (attempt + 1)
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError("Gemini: превышен лимит запросов после 3 попыток")


def _fallback(filename: str) -> dict:
    return {"title": filename, "author": None, "year": None,
            "publisher": None, "category": "Прочее"}


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    if "API_KEY_INVALID" in msg or "invalid" in msg.lower():
        return "Неверный API-ключ"
    if "429" in msg or "quota" in msg.lower():
        return "Лимит запросов (429) — попробуйте позже"
    if "403" in msg:
        return "Доступ запрещён (403)"
    if "404" in msg:
        return f"Модель {MODEL} не найдена (404)"
    return msg[:120]
