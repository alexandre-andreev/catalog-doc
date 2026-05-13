import threading
import tkinter as tk
from tkinter import filedialog
from typing import Callable
import customtkinter as ctk
from config import settings as cfg


class SettingsTab(ctk.CTkFrame):
    def __init__(self, parent, on_taxonomy_reload: Callable[[], None] | None = None):
        super().__init__(parent, fg_color="transparent")
        self._on_taxonomy_reload = on_taxonomy_reload
        self._gemini_var   = tk.StringVar()
        self._groq_var     = tk.StringVar()
        self._openai_var   = tk.StringVar()
        self._deepseek_var = tk.StringVar()
        self._priority     = tk.StringVar(value="gemini")
        self._build_ui()
        self._load_saved()

    # ------------------------------------------------------------------ build

    def _build_ui(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True)
        root = ctk.CTkFrame(scroll, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=40, pady=20)

        ctk.CTkLabel(root, text="Настройки API",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 18))

        # Gemini
        self._gemini_status = self._build_key_block(
            root,
            title="Google Gemini API",
            subtitle="модели: gemini-2.5-flash-lite → gemini-2.5-flash",
            var=self._gemini_var,
            hint="Получить ключ: aistudio.google.com  →  Get API key",
        )

        # Groq
        self._groq_status = self._build_key_block(
            root,
            title="Groq API",
            subtitle="модель: llama-3.3-70b-versatile  |  бесплатно",
            var=self._groq_var,
            hint="Получить ключ: console.groq.com  →  API Keys  →  Create API Key",
        )

        # OpenAI
        self._openai_status = self._build_key_block(
            root,
            title="OpenAI API",
            subtitle="модель: gpt-4o-mini  |  ~$0.05 за 1000 книг  |  500 RPM",
            var=self._openai_var,
            hint="Получить ключ: platform.openai.com  →  API Keys",
        )

        # DeepSeek
        self._deepseek_status = self._build_key_block(
            root,
            title="DeepSeek API",
            subtitle="модель: deepseek-chat  |  ~$0.14/1M токенов  |  60 RPM",
            var=self._deepseek_var,
            hint="Получить ключ: platform.deepseek.com  →  API Keys",
        )

        # Priority
        pf = ctk.CTkFrame(root)
        pf.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(pf, text="Приоритет:", width=100, anchor="w").pack(
            side="left", padx=14, pady=10)
        for label, value in [
            ("Gemini → Groq", "gemini"),
            ("Groq → DeepSeek", "groq"),
            ("OpenAI → Groq", "openai"),
            ("DeepSeek → Groq", "deepseek"),
        ]:
            ctk.CTkRadioButton(pf, text=label,
                               variable=self._priority, value=value).pack(side="left", padx=8)

        # Buttons
        bf = ctk.CTkFrame(root, fg_color="transparent")
        bf.pack(fill="x", pady=(0, 12))

        self._test_btn = ctk.CTkButton(
            bf, text="Проверить подключение", width=210,
            command=self._start_test)
        self._test_btn.pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            bf, text="Сохранить", width=130,
            fg_color="#1a6b3a", hover_color="#145530",
            command=self._save).pack(side="left")

        # Taxonomy
        ctk.CTkFrame(root, height=1, fg_color="gray30").pack(fill="x", pady=(8, 10))
        ctk.CTkLabel(root, text="Таксономия категорий",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 4))

        tax_info = ctk.CTkFrame(root)
        tax_info.pack(fill="x", pady=(0, 6))
        self._tax_status = ctk.CTkLabel(
            tax_info, text=self._taxonomy_status_text(),
            text_color="gray60", anchor="w",
            font=ctk.CTkFont(size=11))
        self._tax_status.pack(side="left", padx=14, pady=8, fill="x", expand=True)

        tax_btns = ctk.CTkFrame(root, fg_color="transparent")
        tax_btns.pack(fill="x", pady=(0, 4))

        ctk.CTkButton(
            tax_btns, text="Экспортировать в Excel", width=200,
            fg_color="gray30", hover_color="gray25",
            command=self._export_taxonomy).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            tax_btns, text="Загрузить из Excel", width=180,
            fg_color="#1a4a6b", hover_color="#153d58",
            command=self._import_taxonomy).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            tax_btns, text="Сбросить (встроенная)", width=190,
            fg_color="#6b1a1a", hover_color="#551515",
            command=self._reset_taxonomy).pack(side="left")

        # Log
        ctk.CTkLabel(root, text="Журнал проверки:",
                     anchor="w", font=ctk.CTkFont(size=12)).pack(fill="x", pady=(8, 4))
        self._log = ctk.CTkTextbox(
            root, height=200, state="disabled",
            font=ctk.CTkFont(family="Consolas", size=11))
        self._log.pack(fill="both", expand=True)

    def _build_key_block(self, parent, title: str, subtitle: str,
                          var: tk.StringVar, hint: str) -> ctk.CTkLabel:
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=(0, 10))

        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(10, 2))

        ctk.CTkLabel(hdr, text=title,
                     font=ctk.CTkFont(size=13, weight="bold"),
                     anchor="w").pack(side="left")
        ctk.CTkLabel(hdr, text=f"  ({subtitle})",
                     text_color="gray55", font=ctk.CTkFont(size=11),
                     anchor="w").pack(side="left")

        status = ctk.CTkLabel(hdr, text="○  не проверен",
                              text_color="gray55",
                              font=ctk.CTkFont(size=11), anchor="e")
        status.pack(side="right")

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 2))

        entry = ctk.CTkEntry(row, textvariable=var, show="•",
                             placeholder_text="Вставьте API-ключ...")
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        show_btn = ctk.CTkButton(row, text="Показать", width=90,
                                 fg_color="gray30", hover_color="gray25")
        show_btn.configure(command=lambda e=entry, b=show_btn: self._toggle_show(e, b))
        show_btn.pack(side="left")

        ctk.CTkLabel(frame, text=hint,
                     text_color="gray45", font=ctk.CTkFont(size=10),
                     anchor="w").pack(fill="x", padx=14, pady=(2, 10))

        return status

    # ---------------------------------------------------------------- actions

    @staticmethod
    def _toggle_show(entry: ctk.CTkEntry, btn: ctk.CTkButton):
        if entry.cget("show") == "•":
            entry.configure(show="")
            btn.configure(text="Скрыть")
        else:
            entry.configure(show="•")
            btn.configure(text="Показать")

    def _load_saved(self):
        cfg.reload()
        self._gemini_var.set(cfg.get("GEMINI_API_KEY"))
        self._groq_var.set(cfg.get("GROQ_API_KEY"))
        self._openai_var.set(cfg.get("GPT_API_KEY"))
        self._deepseek_var.set(cfg.get("DEEPSEEK_API_KEY"))
        self._priority.set(cfg.get("AI_PRIORITY", "gemini"))

    def _save(self):
        cfg.save({
            "GEMINI_API_KEY":   self._gemini_var.get().strip(),
            "GROQ_API_KEY":     self._groq_var.get().strip(),
            "GPT_API_KEY":      self._openai_var.get().strip(),
            "DEEPSEEK_API_KEY": self._deepseek_var.get().strip(),
            "AI_PRIORITY":      self._priority.get(),
        })
        self._log_append("[OK] Настройки сохранены в .env\n")

    # -------------------------------------------------------------- test flow

    def _start_test(self):
        self._test_btn.configure(state="disabled", text="Проверяем...")
        self._log_clear()
        for status in (self._gemini_status, self._groq_status, self._openai_status):
            status.configure(text="○  проверяем...", text_color="gray55")
        threading.Thread(target=self._run_tests, daemon=True).start()

    def _run_tests(self):
        self._test_provider(
            label="Gemini",
            key=self._gemini_var.get().strip(),
            status_widget=self._gemini_status,
            factory=lambda k: __import__("ai.gemini_provider", fromlist=["GeminiProvider"]).GeminiProvider(k),
        )
        self._test_provider(
            label="Groq  ",
            key=self._groq_var.get().strip(),
            status_widget=self._groq_status,
            factory=lambda k: __import__("ai.groq_provider", fromlist=["GroqProvider"]).GroqProvider(k),
        )
        self._test_provider(
            label="OpenAI",
            key=self._openai_var.get().strip(),
            status_widget=self._openai_status,
            factory=lambda k: __import__("ai.openai_provider", fromlist=["OpenAIProvider"]).OpenAIProvider(k),
        )
        self._test_provider(
            label="DeepSeek",
            key=self._deepseek_var.get().strip(),
            status_widget=self._deepseek_status,
            factory=lambda k: __import__("ai.deepseek_provider", fromlist=["DeepSeekProvider"]).DeepSeekProvider(k),
        )
        self.after(0, lambda: self._test_btn.configure(
            state="normal", text="Проверить подключение"))

    def _test_provider(self, label: str, key: str, status_widget, factory):
        if not key:
            self.after(0, lambda: status_widget.configure(
                text="—  ключ не задан", text_color="gray50"))
            self._log_append(f"{label}: ключ не задан — пропускаем\n")
            return

        self._log_append(f"{label}: подключаемся...\n")
        try:
            result = factory(key).test_connection()
        except Exception as e:
            result = str(e)

        if result == "ok":
            self.after(0, lambda: status_widget.configure(
                text="✓  доступен", text_color="#4caf50"))
            self._log_append(f"{label}: OK — соединение установлено\n")
        else:
            self.after(0, lambda: status_widget.configure(
                text="✗  ошибка", text_color="#f44336"))
            self._log_append(f"{label}: {result}\n")

    # --------------------------------------------------------------- log helpers

    def _log_clear(self):
        self.after(0, self._do_log_clear)

    def _do_log_clear(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _log_append(self, text: str):
        self.after(0, lambda t=text: self._do_append(t))

    def _do_append(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text)
        self._log.see("end")
        self._log.configure(state="disabled")

    # --------------------------------------------------------- taxonomy

    @staticmethod
    def _taxonomy_status_text() -> str:
        from utils.taxonomy_excel import custom_exists, CUSTOM_FILE
        if custom_exists():
            try:
                from ai.taxonomy import get_active
                cats, _ = get_active()
                return f"Пользовательская таксономия  |  {len(cats)} категорий  ({CUSTOM_FILE.name})"
            except Exception:
                return "Пользовательская таксономия загружена"
        from ai.taxonomy import CATEGORIES_UI
        return f"Встроенная таксономия  |  {len(CATEGORIES_UI)} категорий"

    def _export_taxonomy(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel файл", "*.xlsx")],
            initialfile="taxonomy.xlsx",
            title="Сохранить таксономию как…",
        )
        if not path:
            return
        try:
            from ai.taxonomy import get_active
            from utils.taxonomy_excel import export_taxonomy
            cats, _ = get_active()
            export_taxonomy(path, cats)
            self._log_append(f"[OK] Таксономия экспортирована: {path}\n"
                             f"     {len(cats)} категорий\n")
            try:
                import os
                os.startfile(path)
            except Exception:
                pass
        except Exception as exc:
            self._log_append(f"[ERR] Ошибка экспорта: {exc}\n")

    def _import_taxonomy(self):
        path = filedialog.askopenfilename(
            filetypes=[("Excel файл", "*.xlsx")],
            title="Выберите файл таксономии…",
        )
        if not path:
            return
        try:
            from utils.taxonomy_excel import load_taxonomy, save_custom
            from ai.taxonomy import apply_custom
            cats, guide = load_taxonomy(path)
            save_custom(cats, guide)
            apply_custom(cats, guide)
            self._tax_status.configure(text=self._taxonomy_status_text(),
                                       text_color="#4caf50")
            self._log_append(f"[OK] Таксономия загружена: {path}\n"
                             f"     {len(cats)} категорий\n")
            if self._on_taxonomy_reload:
                self._on_taxonomy_reload()
        except Exception as exc:
            self._log_append(f"[ERR] Ошибка загрузки: {exc}\n")

    def _reset_taxonomy(self):
        try:
            from utils.taxonomy_excel import reset_custom
            from ai.taxonomy import CATEGORIES_UI, CATEGORY_GUIDE, apply_custom
            reset_custom()
            apply_custom(CATEGORIES_UI, CATEGORY_GUIDE)
            self._tax_status.configure(text=self._taxonomy_status_text(),
                                       text_color="gray60")
            self._log_append("[OK] Таксономия сброшена на встроенную\n")
            if self._on_taxonomy_reload:
                self._on_taxonomy_reload()
        except Exception as exc:
            self._log_append(f"[ERR] Ошибка сброса: {exc}\n")
