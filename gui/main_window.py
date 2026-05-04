import customtkinter as ctk
from gui.scan_tab import ScanTab
from gui.settings_tab import SettingsTab

_PLACEHOLDER_TABS = [
    ("Каталог",   "Раздел «Каталог» будет доступен после этапа 3."),
    ("Дубликаты", "Раздел «Дубликаты» будет доступен после этапа 5."),
    ("Структура", "Раздел «Структура» будет доступен после этапа 6."),
]


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DocArchiver — Каталогизатор электронных книг")
        self.geometry("1280x760")
        self.minsize(960, 620)

        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=10, pady=10)

        self._tabs.add("Сканирование")
        ScanTab(self._tabs.tab("Сканирование")).pack(fill="both", expand=True)

        for name, hint in _PLACEHOLDER_TABS:
            self._tabs.add(name)
            ctk.CTkLabel(
                self._tabs.tab(name), text=hint,
                text_color="gray50", font=ctk.CTkFont(size=14),
            ).place(relx=0.5, rely=0.5, anchor="center")

        self._tabs.add("Настройки")
        SettingsTab(self._tabs.tab("Настройки")).pack(fill="both", expand=True)

        self._tabs.set("Сканирование")
