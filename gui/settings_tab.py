import threading
import tkinter as tk
import customtkinter as ctk
from config import settings as cfg


class SettingsTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._gemini_var = tk.StringVar()
        self._groq_var   = tk.StringVar()
        self._priority   = tk.StringVar(value="gemini")
        self._build_ui()
        self._load_saved()

    # ------------------------------------------------------------------ build

    def _build_ui(self):
        root = ctk.CTkFrame(self, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=40, pady=20)

        ctk.CTkLabel(root, text="Настройки API",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 18))

        # Gemini
        self._gemini_status = self._build_key_block(
            root,
            title="Google Gemini API",
            subtitle="модель: gemini-2.5-flash",
            var=self._gemini_var,
            hint="Получить ключ: aistudio.google.com  →  Get API key",
        )

        # Groq
        self._groq_status = self._build_key_block(
            root,
            title="Groq API",
            subtitle="модель: llama-3.3-70b-versatile",
            var=self._groq_var,
            hint="Получить ключ: console.groq.com  →  API Keys  →  Create API Key",
        )

        # Priority
        pf = ctk.CTkFrame(root)
        pf.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(pf, text="Приоритет:", width=100, anchor="w").pack(
            side="left", padx=14, pady=10)
        ctk.CTkRadioButton(pf, text="Gemini → Groq",
                           variable=self._priority, value="gemini").pack(side="left", padx=14)
        ctk.CTkRadioButton(pf, text="Groq → Gemini",
                           variable=self._priority, value="groq").pack(side="left", padx=4)

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

        # Header row
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

        # Key input row
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
        self._priority.set(cfg.get("AI_PRIORITY", "gemini"))

    def _save(self):
        cfg.save({
            "GEMINI_API_KEY": self._gemini_var.get().strip(),
            "GROQ_API_KEY":   self._groq_var.get().strip(),
            "AI_PRIORITY":    self._priority.get(),
        })
        self._log_append("[OK] Настройки сохранены в .env\n")

    # -------------------------------------------------------------- test flow

    def _start_test(self):
        self._test_btn.configure(state="disabled", text="Проверяем...")
        self._log_clear()
        self._gemini_status.configure(text="○  проверяем...", text_color="gray55")
        self._groq_status.configure(text="○  проверяем...",   text_color="gray55")
        threading.Thread(target=self._run_tests, daemon=True).start()

    def _run_tests(self):
        gemini_key = self._gemini_var.get().strip()
        groq_key   = self._groq_var.get().strip()

        # --- Gemini ---
        if gemini_key:
            self._log_append("Gemini: подключаемся...\n")
            try:
                from ai.gemini_provider import GeminiProvider
                result = GeminiProvider(gemini_key).test_connection()
            except Exception as e:
                result = str(e)

            if result == "ok":
                self.after(0, lambda: self._gemini_status.configure(
                    text="✓  доступен", text_color="#4caf50"))
                self._log_append("Gemini: OK — соединение установлено\n")
            else:
                self.after(0, lambda: self._gemini_status.configure(
                    text="✗  ошибка", text_color="#f44336"))
                self._log_append(f"Gemini: {result}\n")
        else:
            self.after(0, lambda: self._gemini_status.configure(
                text="—  ключ не задан", text_color="gray50"))
            self._log_append("Gemini: ключ не задан — пропускаем\n")

        # --- Groq ---
        if groq_key:
            self._log_append("Groq:   подключаемся...\n")
            try:
                from ai.groq_provider import GroqProvider
                result = GroqProvider(groq_key).test_connection()
            except Exception as e:
                result = str(e)

            if result == "ok":
                self.after(0, lambda: self._groq_status.configure(
                    text="✓  доступен", text_color="#4caf50"))
                self._log_append("Groq:   OK — соединение установлено\n")
            else:
                self.after(0, lambda: self._groq_status.configure(
                    text="✗  ошибка", text_color="#f44336"))
                self._log_append(f"Groq:   {result}\n")
        else:
            self.after(0, lambda: self._groq_status.configure(
                text="—  ключ не задан", text_color="gray50"))
            self._log_append("Groq:   ключ не задан — пропускаем\n")

        self.after(0, lambda: self._test_btn.configure(
            state="normal", text="Проверить подключение"))

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
