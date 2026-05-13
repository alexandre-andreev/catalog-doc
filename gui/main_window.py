import customtkinter as ctk
from gui.scan_tab import ScanTab
from gui.catalog_tab import CatalogTab
from gui.duplicates_tab import DuplicatesTab
from gui.structure_tab import StructureTab
from gui.summary_tab import SummaryTab
from gui.settings_tab import SettingsTab


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("DocArchiver — Каталогизатор электронных книг")
        self.geometry("1280x760")
        self.minsize(960, 620)

        self._tabs = ctk.CTkTabview(self)
        self._tabs.pack(fill="both", expand=True, padx=10, pady=10)

        self._tabs.add("Сканирование")
        self._scan_tab = ScanTab(self._tabs.tab("Сканирование"))
        self._scan_tab.pack(fill="both", expand=True)

        self._tabs.add("Каталог")
        self._catalog_tab = CatalogTab(
            self._tabs.tab("Каталог"),
            get_files=self._scan_tab.get_all_items,
            get_scan_root=self._scan_tab.get_scan_root,
        )
        self._catalog_tab.pack(fill="both", expand=True)

        self._tabs.add("Дубликаты")
        DuplicatesTab(
            self._tabs.tab("Дубликаты"),
            get_files=self._scan_tab.get_files,
        ).pack(fill="both", expand=True)

        self._tabs.add("Структура")
        StructureTab(
            self._tabs.tab("Структура"),
            get_files=self._scan_tab.get_all_items,
        ).pack(fill="both", expand=True)

        self._tabs.add("Саммари")
        SummaryTab(
            self._tabs.tab("Саммари"),
            get_files=self._scan_tab.get_files,
        ).pack(fill="both", expand=True)

        self._tabs.add("Настройки")
        SettingsTab(
            self._tabs.tab("Настройки"),
            on_taxonomy_reload=self._catalog_tab.reload_taxonomy,
        ).pack(fill="both", expand=True)

        self._tabs.set("Сканирование")
