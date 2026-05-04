import customtkinter as ctk
from gui.scan_tab import ScanTab


_PLACEHOLDER_TABS = [
    ("Каталог",    "Раздел «Каталог» будет доступен после этапа 3."),
    ("Дубликаты",  "Раздел «Дубликаты» будет доступен после этапа 5."),
    ("Структура",  "Раздел «Структура» будет доступен после этапа 6."),
    ("Настройки",  "Раздел «Настройки API» будет доступен после этапа 2."),
]


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DocArchiver — Каталогизатор электронных книг")
        self.geometry("1280x760")
        self.minsize(960, 620)

        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=10, pady=10)

        # Stage-1 functional tab
        self._tabs.add("Сканирование")
        self._scan_tab = ScanTab(self._tabs.tab("Сканирование"))
        self._scan_tab.pack(fill="both", expand=True)

        # Placeholder tabs
        for name, hint in _PLACEHOLDER_TABS:
            self._tabs.add(name)
            ctk.CTkLabel(
                self._tabs.tab(name),
                text=hint,
                text_color="gray50",
                font=ctk.CTkFont(size=14),
            ).place(relx=0.5, rely=0.5, anchor="center")

        self._tabs.set("Сканирование")
