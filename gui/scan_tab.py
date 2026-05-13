import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog
import customtkinter as ctk
from core.scanner import Scanner, FileInfo, MediaDirInfo
from core.multipart_detector import detect_multipart_groups

_MULTIPART_WARNING = (
    "Внимание: обнаружены многотомные издания (файлы одной книги, разбитые на части).\n"
    "При необходимости эти части можно объединить в ZIP-архив вручную."
)


class ScanTab(ctk.CTkFrame):
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self._scanner = Scanner()
        self._files: list[FileInfo] = []
        self._media_dirs: list[MediaDirInfo] = []
        self._path_to_iid: dict[str, str] = {}   # full_path -> treeview iid
        self._queue: queue.Queue = queue.Queue()
        self._scan_thread: threading.Thread | None = None
        self._errors: list[str] = []

        self._build_ui()
        self._poll_queue()

    # ------------------------------------------------------------------ build

    def _build_ui(self):
        # --- directory row ---
        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.pack(fill="x", padx=12, pady=(12, 4))

        ctk.CTkLabel(dir_frame, text="Каталог архива:", width=120, anchor="w").pack(side="left")
        self._dir_var = tk.StringVar(value=r"D:\Книги")
        ctk.CTkEntry(dir_frame, textvariable=self._dir_var).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ctk.CTkButton(dir_frame, text="Обзор...", width=90,
                      command=self._browse).pack(side="left")

        # --- controls row ---
        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=12, pady=4)

        self._start_btn = ctk.CTkButton(
            ctrl_frame, text="Начать сканирование", width=190,
            command=self._start_scan
        )
        self._start_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            ctrl_frame, text="Остановить", width=120, state="disabled",
            fg_color="#555", hover_color="#444",
            command=self._stop_scan
        )
        self._stop_btn.pack(side="left")

        self._hash_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            ctrl_frame, text="Вычислять SHA-256", variable=self._hash_var
        ).pack(side="left", padx=20)

        self._stats_label = ctk.CTkLabel(ctrl_frame, text="", text_color="gray60")
        self._stats_label.pack(side="right", padx=8)

        # --- progress ---
        prog_frame = ctk.CTkFrame(self, fg_color="transparent")
        prog_frame.pack(fill="x", padx=12, pady=(0, 4))

        self._progress = ctk.CTkProgressBar(prog_frame)
        self._progress.pack(fill="x")
        self._progress.set(0)

        self._status_label = ctk.CTkLabel(
            prog_frame, text="Готово к сканированию",
            text_color="gray60", anchor="w", font=ctk.CTkFont(size=11)
        )
        self._status_label.pack(fill="x", pady=(2, 0))

        # --- multipart warning (hidden until groups are detected) ---
        self._warn_frame = ctk.CTkFrame(self, fg_color="#3d2800", corner_radius=6)
        # not packed yet — shown only when multipart groups are found

        warn_inner = ctk.CTkFrame(self._warn_frame, fg_color="transparent")
        warn_inner.pack(fill="x", padx=10, pady=6)

        ctk.CTkLabel(
            warn_inner,
            text="!  Многотомные издания",
            text_color="#f0a500",
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
        ).pack(side="left")

        self._warn_detail = ctk.CTkLabel(
            warn_inner, text="", text_color="#c8a060",
            font=ctk.CTkFont(size=11), anchor="w",
        )
        self._warn_detail.pack(side="left", padx=(12, 0))

        ctk.CTkLabel(
            self._warn_frame,
            text=_MULTIPART_WARNING,
            text_color="#c8a060",
            font=ctk.CTkFont(size=11),
            anchor="w", justify="left",
        ).pack(fill="x", padx=10, pady=(0, 8))

        # --- table ---
        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._tree = self._create_tree(table_frame)

    def _create_tree(self, parent) -> ttk.Treeview:
        style = ttk.Style()
        style.theme_use("default")
        bg, fg, sel, head = "#2b2b2b", "#e0e0e0", "#1a5276", "#1f538d"

        style.configure("DA.Treeview",
                        background=bg, foreground=fg, fieldbackground=bg,
                        rowheight=22, borderwidth=0,
                        font=("Segoe UI", 10))
        style.configure("DA.Treeview.Heading",
                        background=head, foreground="white",
                        font=("Segoe UI", 10, "bold"), relief="flat")
        style.map("DA.Treeview", background=[("selected", sel)])
        style.map("DA.Treeview.Heading", background=[("active", "#144578")])

        cols = ("name", "ext", "size_mb", "modified", "sha256", "group", "directory")
        tree = ttk.Treeview(parent, columns=cols, show="headings",
                            style="DA.Treeview", selectmode="browse")

        tree.heading("name",      text="Имя файла / папки", anchor="w")
        tree.heading("ext",       text="Формат",            anchor="center")
        tree.heading("size_mb",   text="Размер, МБ",        anchor="e")
        tree.heading("modified",  text="Изменён",           anchor="w")
        tree.heading("sha256",    text="SHA-256",           anchor="w")
        tree.heading("group",     text="Группа",            anchor="center")
        tree.heading("directory", text="Каталог",           anchor="w")

        tree.column("name",      width=280, minwidth=120, stretch=False)
        tree.column("ext",       width=65,  minwidth=50,  anchor="center", stretch=False)
        tree.column("size_mb",   width=90,  minwidth=70,  anchor="e",      stretch=False)
        tree.column("modified",  width=130, minwidth=100,                  stretch=False)
        tree.column("sha256",    width=130, minwidth=80,                   stretch=False)
        tree.column("group",     width=80,  minwidth=60,  anchor="center", stretch=False)
        tree.column("directory", width=520, minwidth=150, stretch=False)

        tree.tag_configure("multipart",  background="#3a2200", foreground="#f0c060")
        tree.tag_configure("media_dir",  background="#1a2a1a", foreground="#80d080")

        vsb = ttk.Scrollbar(parent, orient="vertical",   command=tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(fill="both", expand=True)

        for col in cols:
            tree.heading(col, command=lambda c=col: self._sort_by(c))

        return tree

    # --------------------------------------------------------------- actions

    def _browse(self):
        path = filedialog.askdirectory(title="Выберите корневой каталог архива")
        if path:
            self._dir_var.set(path.replace("/", "\\"))

    def _start_scan(self):
        root = self._dir_var.get().strip()
        if not root:
            return

        self._files.clear()
        self._media_dirs.clear()
        self._path_to_iid.clear()
        self._errors.clear()
        for item in self._tree.get_children():
            self._tree.delete(item)

        self._warn_frame.pack_forget()

        self._start_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._progress.set(0)
        self._status_label.configure(text="Инициализация — подсчёт файлов...")
        self._stats_label.configure(text="")

        compute_hashes = self._hash_var.get()
        self._scan_thread = threading.Thread(
            target=self._run_scan, args=(root, compute_hashes), daemon=True
        )
        self._scan_thread.start()

    def _run_scan(self, root: str, compute_hashes: bool):
        # Phase 1: scan document files
        self._scanner.scan(
            root,
            compute_hashes=compute_hashes,
            on_progress=lambda cur, tot, fp: self._queue.put(("progress", cur, tot, fp)),
            on_file_found=lambda info: self._queue.put(("file", info)),
            on_done=lambda results: self._queue.put(("files_done", results)),
            on_error=lambda fp, err: self._queue.put(("error", fp, err)),
        )
        if self._scanner.is_stopped:
            self._queue.put(("done",))
            return
        # Phase 2: scan media directories
        self._queue.put(("media_scan_start",))
        self._scanner.scan_media_dirs(
            root,
            on_found=lambda info: self._queue.put(("media_found", info)),
            on_done=lambda results: self._queue.put(("done",)),
        )

    def _stop_scan(self):
        self._scanner.stop()
        self._stop_btn.configure(state="disabled")
        self._status_label.configure(text="Остановка...")

    # ----------------------------------------------------------- queue pump

    def _poll_queue(self):
        try:
            for _ in range(50):
                msg = self._queue.get_nowait()
                kind = msg[0]

                if kind == "progress":
                    _, cur, tot, fp = msg
                    if tot:
                        self._progress.set(cur / tot * 0.9)  # 0–90% for file scan
                    short = fp if len(fp) <= 80 else "..." + fp[-77:]
                    self._status_label.configure(text=f"{cur}/{tot}  {short}")

                elif kind == "file":
                    info: FileInfo = msg[1]
                    self._files.append(info)
                    self._insert_row(info)
                    self._stats_label.configure(
                        text=f"{len(self._files)} файлов  |  "
                             f"{sum(f.size_mb for f in self._files):.1f} МБ"
                    )

                elif kind == "files_done":
                    results: list[FileInfo] = msg[1]
                    self._apply_multipart(results)

                elif kind == "media_scan_start":
                    self._status_label.configure(
                        text="Поиск медиа-каталогов (курсов)…")

                elif kind == "media_found":
                    info: MediaDirInfo = msg[1]
                    self._media_dirs.append(info)
                    self._insert_media_row(info)
                    self._stats_label.configure(
                        text=f"{len(self._files)} файлов  |  "
                             f"{len(self._media_dirs)} медиа-папок  |  "
                             f"{sum(f.size_mb for f in self._files):.1f} МБ"
                    )

                elif kind == "done":
                    self._progress.set(1.0)
                    stopped = self._scanner.is_stopped
                    verb = "Остановлено" if stopped else "Завершено"
                    errs = f"  |  ошибок: {len(self._errors)}" if self._errors else ""
                    media_str = (f"  |  медиа-папок: {len(self._media_dirs)}"
                                 if self._media_dirs else "")
                    self._status_label.configure(
                        text=f"{verb}. Файлов: {len(self._files)}{media_str}{errs}."
                    )
                    self._start_btn.configure(state="normal")
                    self._stop_btn.configure(state="disabled")

                elif kind == "error":
                    _, fp, err = msg
                    self._errors.append(f"{fp}: {err}")

        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_queue)

    # ---------------------------------------------------------- multipart

    def _apply_multipart(self, results: list[FileInfo]):
        groups = detect_multipart_groups(results)
        if not groups:
            return

        for info in self._files:
            gid = groups.get(info.full_path)
            if not gid:
                continue
            info.group_id = gid
            iid = self._path_to_iid.get(info.full_path)
            if not iid:
                continue
            vals = list(self._tree.item(iid, "values"))
            vals[5] = gid
            self._tree.item(iid, values=vals, tags=("multipart",))

        unique_groups = len(set(groups.values()))
        total_files = len(groups)
        self._warn_detail.configure(
            text=f"обнаружено {unique_groups} изданий ({total_files} файлов)"
        )
        self._warn_frame.pack(fill="x", padx=12, pady=(0, 6), before=self._tree.master)

    # ---------------------------------------------------------- table helpers

    def _insert_row(self, info: FileInfo):
        sha_short = (info.sha256[:16] + "…") if info.sha256 else "—"
        iid = self._tree.insert("", "end", values=(
            info.name,
            info.extension,
            f"{info.size_mb:.2f}",
            info.modified.strftime("%Y-%m-%d %H:%M"),
            sha_short,
            "",
            info.directory,
        ))
        self._path_to_iid[info.full_path] = iid

    def _insert_media_row(self, info: MediaDirInfo):
        iid = self._tree.insert("", "end", values=(
            f"📁  {info.name}",
            "МЕДИА",
            f"{info.size_mb:.2f}",
            info.modified.strftime("%Y-%m-%d %H:%M"),
            f"{info.media_count} файлов",
            "—",
            info.directory,
        ), tags=("media_dir",))
        self._path_to_iid[info.full_path] = iid

    _sort_reverse: dict[str, bool] = {}

    def _sort_by(self, col: str):
        rev = self._sort_reverse.get(col, False)
        items = [(self._tree.set(k, col), k) for k in self._tree.get_children("")]
        try:
            items.sort(key=lambda x: float(x[0].replace("—", "0")), reverse=rev)
        except ValueError:
            items.sort(key=lambda x: x[0].lower(), reverse=rev)
        for idx, (_, k) in enumerate(items):
            self._tree.move(k, "", idx)
        self._sort_reverse[col] = not rev

    # ---------------------------------------------------------- public API

    def get_files(self) -> list[FileInfo]:
        """Document files only (for DuplicatesTab, SummaryTab)."""
        return list(self._files)

    def get_all_items(self) -> list[FileInfo | MediaDirInfo]:
        """All items including media directories (for CatalogTab, StructureTab)."""
        return list(self._files) + list(self._media_dirs)

    def get_scan_root(self) -> str:
        """Return the currently configured scan root directory."""
        return self._dir_var.get().strip()
