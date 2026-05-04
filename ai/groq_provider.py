import json
from groq import Groq

# Primary model, fallback in order
_MODELS = ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"]

_CLASSIFY_PROMPT = """\
Ты — библиотечный каталогизатор. Верни ТОЛЬКО JSON без markdown.

Файл: {filename}
Текст: {text}

Формат:
{{"title": "...", "author": "...", "year": "...", "publisher": "...", "category": "..."}}
Категории: Программирование/Python | Программирование/Web | Базы данных | Системное администрирование | Математика | Машинное обучение | Управление проектами | Художественная литература | Прочее
"""


class GroqProvider:
    def __init__(self, api_key: str):
        self._client = Groq(api_key=api_key)
        self._model = _MODELS[0]

    def test_connection(self) -> str:
        """Returns 'ok' or error description."""
        try:
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "Reply with the word OK only."}],
                max_tokens=10,
                temperature=0,
            )
            _ = resp.choices[0].message.content
            return "ok"
        except Exception as e:
            return _friendly_error(e)

    def classify(self, filename: str, text: str) -> dict:
        prompt = _CLASSIFY_PROMPT.format(filename=filename, text=text[:1500])
        last_err = None
        for model in _MODELS:
            try:
                resp = self._client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=300,
                )
                raw = resp.choices[0].message.content.strip()
                return json.loads(raw)
            except json.JSONDecodeError:
                return _fallback(filename)
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(f"Groq: все модели недоступны. Последняя ошибка: {last_err}")


def _fallback(filename: str) -> dict:
    return {"title": filename, "author": None, "year": None,
            "publisher": None, "category": "Прочее"}


def _friendly_error(exc: Exception) -> str:
    msg = str(exc)
    if "invalid_api_key" in msg or "401" in msg:
        return "Неверный API-ключ"
    if "429" in msg or "rate" in msg.lower():
        return "Лимит запросов (429) — попробуйте позже"
    if "403" in msg:
        return "Доступ запрещён (403)"
    return msg[:120]
