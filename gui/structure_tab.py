import os
import queue
import shutil
import threading
import tkinter as tk
from collections import defaultdict
from pathlib import Path
from tkinter import ttk, filedialog
from typing import Callable

_UNC = "\\\\?\\"   # Windows long-path prefix (bypasses MAX_PATH=260)


def _long(path: str) -> str:
    """Return path with UNC prefix so Windows allows >260-char paths."""
    abs_path = os.path.abspath(path)
    if abs_path.startswith(_UNC):
        return abs_path
    return _UNC + abs_path

import customtkinter as ctk

from core.scanner import FileInfo, MediaDirInfo
from utils import cache as cache_utils


def _sanitize(name: str) -> str:
    """Remove characters invalid in Windows directory names."""
    for ch in r'\/:*?"<>|':
        name = name.replace(ch, "_")
    return name.strip(" .")[:80] or "_"


def _resolve_conflict(filename: str, target_dir: str) -> str:
    """Return a filename that doesn't collide with existing files in target_dir."""
    if not os.path.exists(_long(os.path.join(target_dir, filename))):
        return filename
    stem, ext = Path(filename).stem, Path(filename).suffix
    n = 2
    while True:
        candidate = f"{stem} ({n}){ext}"
        if not os.path.exists(_long(os.path.join(target_dir, candidate))):
            return candidate
        n += 1


def _resolve_dir_conflict(dirname: str, target_dir: str) -> str:
    """Return a directory name that doesn't collide with existing entries in target_dir."""
    if not os.path.exists(_long(os.path.join(target_dir, dirname))):
        return dirname
    n = 2
    while True:
        candidate = f"{dirname} ({n})"
        if not os.path.exists(_long(os.path.join(target_dir, candidate))):
            return candidate
        n += 1


class StructureTab(ctk.CTkFrame):
    def __init__(self, parent, get_files: Callable[[], list[FileInfo | MediaDirInfo]]):
        super().__init__(parent, fg_color="transparent")
        self._get_files = get_files
        self._files: list[FileInfo] = []
        # plan: relative_dir → list[FileInfo]
        self._plan: dict[str, list[FileInfo]] = {}
        self._queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()
        self._running = False

        self._build_ui()
        self._poll_queue()

    # ---------------------------------------------------------------- build ui

    def _build_ui(self):
        # top: load buttons + stats
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 2))

        ctk.CTkButton(top, text="Загрузить из сканирования", width=215,
                      command=self._load_from_scan).pack(side="left", padx=(0, 8))
        ctk.CTkButton(top, text="Загрузить с диска", width=150,
                      fg_color="gray30", hover_color="gray25",
                      command=self._load_from_disk).pack(side="left", padx=(0, 8))

        self._stats_label = ctk.CTkLabel(
            top, text="Загрузите классифицированные файлы", text_color="gray60")
        self._stats_label.pack(side="right", padx=12)

        # root dir picker
        dir_frame = ctk.CTkFrame(self, fg_color="transparent")
        dir_frame.pack(fill="x", padx=12, pady=(4, 4))

        ctk.CTkLabel(dir_frame, text="Корневой каталог:", width=135,
                     anchor="w").pack(side="left")
        self._root_var = tk.StringVar()
        ctk.CTkEntry(dir_frame, textvariable=self._root_var,
                     placeholder_text="Укажите путь для новой структуры…"
                     ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(dir_frame, text="Обзор…", width=90,
                      command=self._browse_root).pack(side="left")

        # action row
        act = ctk.CTkFrame(self, fg_color="transparent")
        act.pack(fill="x", padx=12, pady=(0, 4))

        self._run_btn = ctk.CTkButton(
            act, text="Реструктурировать каталог →", width=230, state="disabled",
            fg_color="#1a5c1a", hover_color="#144d14",
            command=self._start_restructure)
        self._run_btn.pack(side="left", padx=(0, 8))

        self._stop_btn = ctk.CTkButton(
            act, text="Стоп", width=80, state="disabled",
            fg_color="#555", hover_color="#444",
            command=self._stop_restructure)
        self._stop_btn.pack(side="left", padx=(0, 16))

        self._action_label = ctk.CTkLabel(
            act, text="", text_color="gray60", font=ctk.CTkFont(size=11))
        self._action_label.pack(side="left")

        # progress bar
        prog = ctk.CTkFrame(self, fg_color="transparent")
        prog.pack(fill="x", padx=12, pady=(0, 4))

        self._progress = ctk.CTkProgressBar(prog)
        self._progress.pack(fill="x")
        self._progress.set(0)

        self._status_label = ctk.CTkLabel(
            prog, text="", text_color="gray60",
            anchor="w", font=ctk.CTkFont(size=11))
        self._status_label.pack(fill="x", pady=(2, 0))

        # main: tree (left) + log (right)
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        tree_frame = ctk.CTkFrame(main)
        tree_frame.pack(side="left", fill="both", expand=True)
        self._tree = self._create_tree(tree_frame)

        right = ctk.CTkFrame(main, width=310)
        right.pack(side="right", fill="y", padx=(8, 0))
        right.pack_propagate(False)
        self._build_log_panel(right)

    def _create_tree(self, parent) -> ttk.Treeview:
        style = ttk.Style()
        bg, fg, sel, head = "#2b2b2b", "#e0e0e0", "#1a5276", "#1f538d"

        style.configure("STR.Treeview",
                        background=bg, foreground=fg, fieldbackground=bg,
                        rowheight=22, borderwidth=0, font=("Segoe UI", 10))
        style.configure("STR.Treeview.Heading",
                        background=head, foreground="white",
                        font=("Segoe UI", 10, "bold"), relief="flat")
        style.map("STR.Treeview", background=[("selected", sel)])
        style.map("STR.Treeview.Heading", background=[("active", "#144578")])

        cols = ("count", "size_mb")
        tree = ttk.Treeview(parent, columns=cols, show="tree headings",
                            style="STR.Treeview", selectmode="browse")

        tree.heading("#0",       text="Структура каталогов", anchor="w")
        tree.heading("count",    text="Файлов",              anchor="e")
        tree.heading("size_mb",  text="МБ",                  anchor="e")

        tree.column("#0",       width=480, minwidth=200, stretch=True)
        tree.column("count",    width=80,  minwidth=55,  anchor="e", stretch=False)
        tree.column("size_mb",  width=90,  minwidth=60,  anchor="e", stretch=False)

        tree.tag_configure("tag_root",
                           background="#142030", foreground="#80c0e8",
                           font=("Segoe UI", 11, "bold"))
        tree.tag_configure("tag_section",
                           background="#1e2a1e", foreground="#90d090",
                           font=("Segoe UI", 10, "bold"))
        tree.tag_configure("tag_sub",
                           background="#2b2b2b", foreground="#d0d0d0")
        tree.tag_configure("tag_nocat",
                           background="#2a1a1a", foreground="#c08080",
                           font=("Segoe UI", 10, "italic"))

        vsb = ttk.Scrollbar(parent, orient="vertical",   command=tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(fill="both", expand=True)

        return tree

    def _build_log_panel(self, parent):
        ctk.CTkLabel(parent, text="Журнал операций",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").pack(fill="x", padx=10, pady=(8, 4))

        self._log_box = ctk.CTkTextbox(
            parent, fg_color="#1a1a2a", border_width=0,
            font=ctk.CTkFont(family="Consolas", size=9),
            wrap="none", state="disabled")
        self._log_box.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkButton(btn_row, text="Сохранить журнал", width=140,
                      fg_color="gray28", hover_color="gray22",
                      command=self._save_log).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="Очистить", width=80,
                      fg_color="gray28", hover_color="gray22",
                      command=self._clear_log).pack(side="left")

    # ---------------------------------------------------------------- load

    def _load_from_scan(self):
        files = self._get_files()
        if not files:
            self._stats_label.configure(
                text="Нет файлов — сначала выполните сканирование")
            return
        self._populate(files)

    def _load_from_disk(self):
        files, _ = cache_utils.load_file_list()
        if not files:
            self._stats_label.configure(
                text="Сохранённый список не найден — выполните сканирование")
            return
        self._populate(files)

    def _populate(self, files: list[FileInfo]):
        self._files = files
        cache = cache_utils.load()

        # Build plan: rel_dir → [FileInfo]
        plan: dict[str, list[FileInfo]] = defaultdict(list)
        no_cat: list[FileInfo] = []

        for f in files:
            cached = cache_utils.get_cached(f, cache)
            category = (cached.get("category") or "").strip() if cached else ""
            if not category:
                no_cat.append(f)
                continue
            if "/" in category:
                section, sub = category.split("/", 1)
                rel = os.path.join(_sanitize(section), _sanitize(sub))
            else:
                rel = _sanitize(category)
            plan[rel].append(f)

        if no_cat:
            plan["Без категории"] = no_cat

        self._plan = dict(plan)
        self._build_preview_tree()

        classified = len(files) - len(no_cat)
        dirs = len(plan)
        total_mb = sum(f.size_mb for f in files)
        self._stats_label.configure(
            text=(f"{len(files)} файлов  •  классифицировано: {classified}  •  "
                  f"{dirs} папок  •  {total_mb:.1f} МБ"))
        self._update_run_btn()

    def _browse_root(self):
        path = filedialog.askdirectory(title="Выберите место для корневого каталога")
        if path:
            self._root_var.set(path.replace("/", "\\"))
            self._update_run_btn()

    # ---------------------------------------------------------------- preview tree

    def _build_preview_tree(self):
        for item in self._tree.get_children():
            self._tree.delete(item)

        if not self._plan:
            return

        total_files = sum(len(v) for v in self._plan.values())
        total_mb    = sum(f.size_mb for files in self._plan.values() for f in files)

        root_display = Path(self._root_var.get().strip()).name if self._root_var.get().strip() \
            else "<корневой каталог>"
        root_iid = self._tree.insert(
            "", "end",
            text=f"📁  {root_display}",
            values=(str(total_files), f"{total_mb:.1f}"),
            open=True, tags=("tag_root",))

        # Group plan into 2-level structure: section → {sub_or_None → files}
        sections: dict[str, dict] = {}
        for rel_dir, files in self._plan.items():
            parts = Path(rel_dir).parts
            section = parts[0]
            sub = parts[1] if len(parts) > 1 else None
            sections.setdefault(section, {})[sub] = files

        # Sort: regular sections alphabetically, "Без категории" last
        ordered = sorted(
            (s for s in sections if s != "Без категории"), key=str.lower)
        if "Без категории" in sections:
            ordered.append("Без категории")

        for section in ordered:
            subs = sections[section]
            sec_files = sum(len(f) for f in subs.values())
            sec_mb    = sum(fi.size_mb for files in subs.values() for fi in files)
            tag = "tag_nocat" if section == "Без категории" else "tag_section"

            sec_iid = self._tree.insert(
                root_iid, "end",
                text=f"📁  {section}",
                values=(str(sec_files), f"{sec_mb:.1f}"),
                open=True, tags=(tag,))

            for sub, files in sorted(
                    ((k, v) for k, v in subs.items() if k is not None),
                    key=lambda x: x[0].lower()):
                sub_mb = sum(f.size_mb for f in files)
                self._tree.insert(
                    sec_iid, "end",
                    text=f"📁  {sub}",
                    values=(str(len(files)), f"{sub_mb:.1f}"),
                    open=True, tags=("tag_sub",))

    # ---------------------------------------------------------------- restructure

    def _update_run_btn(self):
        ready = bool(self._plan and self._root_var.get().strip() and not self._running)
        self._run_btn.configure(state="normal" if ready else "disabled")

    def _start_restructure(self):
        root = self._root_var.get().strip()
        if not root or not self._plan:
            return
        if os.path.normpath(root) in [
                os.path.normpath(f.directory) for files in self._plan.values()
                for f in files]:
            self._status_label.configure(
                text="⚠  Корневой каталог совпадает с одной из исходных папок — укажите другое место",
                text_color="#f0a500")
            return

        self._running = True
        self._stop_event.clear()
        self._run_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        self._progress.set(0)
        self._status_label.configure(text="Начинаем…", text_color="gray60")
        self._log("=" * 50)
        self._log(f"Цель: {root}")
        self._log(f"Файлов к копированию: {sum(len(v) for v in self._plan.values())}")
        self._log("=" * 50)

        threading.Thread(
            target=self._run_copy, args=(root, dict(self._plan)),
            daemon=True).start()

    def _stop_restructure(self):
        self._stop_event.set()
        self._stop_btn.configure(state="disabled")
        self._status_label.configure(text="Остановка…", text_color="gray60")

    def _run_copy(self, root: str, plan: dict[str, list[FileInfo]]):
        total = sum(len(v) for v in plan.items())   # counts entries (wrong)
        total = sum(len(v) for v in plan.values())
        done = 0
        errors: list[tuple[str, str]] = []

        for rel_dir, files in plan.items():
            if self._stop_event.is_set():
                break
            target_dir = os.path.join(root, rel_dir)
            try:
                os.makedirs(_long(target_dir), exist_ok=True)
            except Exception as e:
                for f in files:
                    errors.append((f.full_path, f"Не удалось создать папку: {e}"))
                    done += 1
                    self._queue.put(("progress", done, total, f.name))
                continue

            for f in files:
                if self._stop_event.is_set():
                    break
                if getattr(f, "is_media_dir", False):
                    # Copy the entire media directory as one unit
                    target_name = _resolve_dir_conflict(f.name, target_dir)
                    target_path = os.path.join(target_dir, target_name)
                    try:
                        shutil.copytree(_long(f.full_path), _long(target_path))
                        renamed = target_name != f.name
                        self._queue.put(("copied", done + 1, total,
                                         f"📁 {f.name}", rel_dir, target_name, renamed))
                    except Exception as e:
                        errors.append((f.full_path, str(e)))
                        self._queue.put(("error_file", done + 1, total, f.name, str(e)))
                else:
                    target_name = _resolve_conflict(f.name, target_dir)
                    target_path = os.path.join(target_dir, target_name)
                    try:
                        shutil.copy2(_long(f.full_path), _long(target_path))
                        renamed = target_name != f.name
                        self._queue.put(("copied", done + 1, total, f.name,
                                         rel_dir, target_name, renamed))
                    except Exception as e:
                        errors.append((f.full_path, str(e)))
                        self._queue.put(("error_file", done + 1, total, f.name, str(e)))
                done += 1

        self._queue.put(("done", done, total, errors))

    # ---------------------------------------------------------------- queue pump

    def _poll_queue(self):
        try:
            for _ in range(40):
                msg = self._queue.get_nowait()
                kind = msg[0]

                if kind == "copied":
                    _, cur, tot, name, rel_dir, target_name, renamed = msg
                    self._progress.set(cur / tot if tot else 0)
                    self._status_label.configure(
                        text=f"Копирую {cur}/{tot}:  {name}")
                    if renamed:
                        self._log(f"[переименован]  {name}  →  {rel_dir}\\{target_name}")
                    else:
                        self._log(f"✓  {name}  →  {rel_dir}\\")

                elif kind == "error_file":
                    _, cur, tot, name, err = msg
                    self._progress.set(cur / tot if tot else 0)
                    self._log(f"✗  ОШИБКА: {name} — {err}")

                elif kind == "progress":
                    _, cur, tot, name = msg
                    self._progress.set(cur / tot if tot else 0)
                    self._status_label.configure(text=f"{cur}/{tot}:  {name}")

                elif kind == "done":
                    _, done, total, errors = msg
                    self._progress.set(1.0)
                    stopped = self._stop_event.is_set()
                    verb = "Остановлено" if stopped else "Завершено"
                    ok = done - len(errors)
                    self._status_label.configure(
                        text=f"{verb}. Скопировано: {ok}/{total}"
                        + (f"  •  ошибок: {len(errors)}" if errors else ""),
                        text_color="gray60")
                    self._log("=" * 50)
                    self._log(f"{verb}. Скопировано: {ok}, ошибок: {len(errors)}")
                    if errors:
                        for fp, err in errors[:10]:
                            self._log(f"  ✗  {Path(fp).name}: {err}")
                        if len(errors) > 10:
                            self._log(f"  … и ещё {len(errors) - 10} ошибок")
                    self._log("=" * 50)
                    self._running = False
                    self._stop_btn.configure(state="disabled")
                    self._update_run_btn()

        except queue.Empty:
            pass
        finally:
            self.after(120, self._poll_queue)

    # ---------------------------------------------------------------- log

    def _log(self, text: str):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", text + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _save_log(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Текстовый файл", "*.txt")],
            initialfile="restructure_log.txt",
            title="Сохранить журнал…",
        )
        if not path:
            return
        self._log_box.configure(state="normal")
        content = self._log_box.get("1.0", "end")
        self._log_box.configure(state="disabled")
        try:
            Path(path).write_text(content, encoding="utf-8")
            self._action_label.configure(text=f"Журнал сохранён: {path}")
        except Exception as exc:
            self._action_label.configure(text=f"Ошибка сохранения: {exc}")

    def _clear_log(self):
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        self._log_box.configure(state="disabled")
