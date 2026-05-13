import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Callable

import customtkinter as ctk

from core.scanner import FileInfo
from core.duplicate_finder import DupGroup, find_duplicates, find_by_name_size
from utils import cache as cache_utils

_MARK_DELETE = "✗  Удалить"
_MARK_KEEP   = "✓  Оставить"
_MARK_NONE   = "—"


def _send_to_trash(path: str):
    try:
        from send2trash import send2trash
        send2trash(path)
    except ImportError:
        os.remove(path)


class DuplicatesTab(ctk.CTkFrame):
    def __init__(self, parent, get_files: Callable[[], list[FileInfo]]):
        super().__init__(parent, fg_color="transparent")
        self._get_files = get_files
        self._groups: list[DupGroup] = []
        self._to_delete: set[str] = set()
        self._to_keep: set[str] = set()
        self._selected_path: str | None = None

        # tree ↔ data maps
        self._iid_to_file: dict[str, FileInfo] = {}   # child iid → FileInfo
        self._iid_to_gidx: dict[str, int] = {}        # child iid → group index
        self._file_to_iid: dict[str, str] = {}        # full_path → child iid

        self._build_ui()

    # ---------------------------------------------------------------- build ui

    def _build_ui(self):
        # top: load buttons
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 2))

        ctk.CTkButton(top, text="Загрузить из сканирования", width=215,
                      command=self._load_from_scan).pack(side="left", padx=(0, 8))
        ctk.CTkButton(top, text="Загрузить с диска", width=150,
                      fg_color="gray30", hover_color="gray25",
                      command=self._load_from_disk).pack(side="left", padx=(0, 8))

        self._stats_label = ctk.CTkLabel(
            top, text="Загрузите файлы для поиска дубликатов", text_color="gray60")
        self._stats_label.pack(side="right", padx=12)

        # action bar
        act = ctk.CTkFrame(self, fg_color="transparent")
        act.pack(fill="x", padx=12, pady=(0, 4))

        self._auto_btn = ctk.CTkButton(
            act, text="Авто-выбор (оставить новейшие)", width=240, state="disabled",
            command=self._auto_select)
        self._auto_btn.pack(side="left", padx=(0, 8))

        self._clear_btn = ctk.CTkButton(
            act, text="Снять все отметки", width=160, state="disabled",
            fg_color="gray30", hover_color="gray25",
            command=self._clear_marks)
        self._clear_btn.pack(side="left", padx=(0, 8))

        self._delete_btn = ctk.CTkButton(
            act, text="Удалить отмеченные", width=185, state="disabled",
            fg_color="#6b1a1a", hover_color="#551515",
            command=self._delete_marked)
        self._delete_btn.pack(side="left")

        self._action_label = ctk.CTkLabel(act, text="", text_color="gray60",
                                           font=ctk.CTkFont(size=11))
        self._action_label.pack(side="left", padx=16)

        # main: tree + right panel
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        tree_frame = ctk.CTkFrame(main)
        tree_frame.pack(side="left", fill="both", expand=True)
        self._tree = self._create_tree(tree_frame)

        right = ctk.CTkFrame(main, width=275)
        right.pack(side="right", fill="y", padx=(8, 0))
        right.pack_propagate(False)
        self._build_right_panel(right)

    def _create_tree(self, parent) -> ttk.Treeview:
        style = ttk.Style()
        bg, fg, sel, head = "#2b2b2b", "#e0e0e0", "#1a5276", "#1f538d"

        style.configure("DUP.Treeview",
                        background=bg, foreground=fg, fieldbackground=bg,
                        rowheight=22, borderwidth=0, font=("Segoe UI", 10))
        style.configure("DUP.Treeview.Heading",
                        background=head, foreground="white",
                        font=("Segoe UI", 10, "bold"), relief="flat")
        style.map("DUP.Treeview", background=[("selected", sel)])
        style.map("DUP.Treeview.Heading", background=[("active", "#144578")])

        cols = ("mark", "size_mb", "modified", "directory")
        tree = ttk.Treeview(parent, columns=cols, show="tree headings",
                            style="DUP.Treeview", selectmode="browse")

        tree.heading("#0",        text="Группа / Имя файла", anchor="w")
        tree.heading("mark",      text="Отметка",            anchor="center")
        tree.heading("size_mb",   text="МБ",                 anchor="e")
        tree.heading("modified",  text="Изменён",            anchor="w")
        tree.heading("directory", text="Папка",              anchor="w")

        tree.column("#0",        width=290, minwidth=150, stretch=False)
        tree.column("mark",      width=105, minwidth=80,  anchor="center", stretch=False)
        tree.column("size_mb",   width=72,  minwidth=50,  anchor="e",      stretch=False)
        tree.column("modified",  width=130, minwidth=90,  stretch=False)
        tree.column("directory", width=400, minwidth=150, stretch=True)

        tree.tag_configure("tag_group",
                           background="#142030", foreground="#80b8e0",
                           font=("Segoe UI", 10, "bold"))
        tree.tag_configure("tag_keep",   background="#132313", foreground="#70d070")
        tree.tag_configure("tag_delete", background="#2a1010", foreground="#e08080")
        tree.tag_configure("tag_plain",  background="#2b2b2b", foreground="#c0c0c0")

        vsb = ttk.Scrollbar(parent, orient="vertical",   command=tree.yview)
        hsb = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right",  fill="y")
        hsb.pack(side="bottom", fill="x")
        tree.pack(fill="both", expand=True)

        tree.bind("<<TreeviewSelect>>", self._on_select)
        tree.bind("<Double-Button-1>",  self._on_double_click)
        tree.bind("<Button-3>",         self._on_right_click)

        self._ctx_menu = tk.Menu(tree, tearoff=0)
        self._ctx_menu.add_command(label="Открыть файл",           command=self._open_file)
        self._ctx_menu.add_command(label="Показать в проводнике",  command=self._open_folder)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Копировать путь",        command=self._copy_path)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="✓  Оставить этот файл",  command=self._mark_keep)
        self._ctx_menu.add_command(label="✗  Отметить для удаления", command=self._mark_delete)

        return tree

    def _build_right_panel(self, parent):
        ctk.CTkLabel(parent, text="Выбранный файл",
                     font=ctk.CTkFont(size=11, weight="bold"),
                     anchor="w").pack(fill="x", padx=10, pady=(8, 4))

        self._rp_name = ctk.CTkLabel(parent, text="—", anchor="w",
                                      font=ctk.CTkFont(size=10, weight="bold"),
                                      wraplength=255)
        self._rp_name.pack(fill="x", padx=10)

        self._rp_path = ctk.CTkLabel(parent, text="", anchor="w",
                                      font=ctk.CTkFont(size=9), text_color="gray50",
                                      wraplength=255)
        self._rp_path.pack(fill="x", padx=10, pady=(1, 0))

        self._rp_info = ctk.CTkLabel(parent, text="", anchor="w",
                                      font=ctk.CTkFont(size=9), text_color="gray55",
                                      wraplength=255)
        self._rp_info.pack(fill="x", padx=10, pady=(1, 6))

        ctk.CTkFrame(parent, height=1, fg_color="gray35").pack(fill="x", padx=10, pady=(0, 8))

        self._keep_btn = ctk.CTkButton(
            parent, text="✓  Оставить этот файл", state="disabled",
            fg_color="#1a4a1a", hover_color="#153815",
            command=self._mark_keep)
        self._keep_btn.pack(fill="x", padx=10, pady=(0, 5))

        self._del_btn = ctk.CTkButton(
            parent, text="✗  Отметить для удаления", state="disabled",
            fg_color="#4a1a1a", hover_color="#3a1010",
            command=self._mark_delete)
        self._del_btn.pack(fill="x", padx=10, pady=(0, 12))

        ctk.CTkFrame(parent, height=1, fg_color="gray35").pack(fill="x", padx=10, pady=(0, 8))

        self._open_btn = ctk.CTkButton(
            parent, text="Открыть файл", state="disabled",
            fg_color="gray28", hover_color="gray22",
            command=self._open_file)
        self._open_btn.pack(fill="x", padx=10, pady=(0, 5))

        self._folder_btn = ctk.CTkButton(
            parent, text="Показать в проводнике", state="disabled",
            fg_color="gray28", hover_color="gray22",
            command=self._open_folder)
        self._folder_btn.pack(fill="x", padx=10, pady=(0, 5))

        self._copy_btn = ctk.CTkButton(
            parent, text="Копировать путь", state="disabled",
            fg_color="gray28", hover_color="gray22",
            command=self._copy_path)
        self._copy_btn.pack(fill="x", padx=10, pady=(0, 12))

        ctk.CTkFrame(parent, height=1, fg_color="gray35").pack(fill="x", padx=10, pady=(0, 8))

        ctk.CTkLabel(parent, text="В этой группе:", anchor="w",
                     font=ctk.CTkFont(size=10, weight="bold")).pack(fill="x", padx=10)
        self._rp_group = ctk.CTkLabel(parent, text="—", anchor="w",
                                       font=ctk.CTkFont(size=9), text_color="gray55",
                                       wraplength=255)
        self._rp_group.pack(fill="x", padx=10, pady=(2, 0))

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
        self._groups.clear()
        self._to_delete.clear()
        self._to_keep.clear()
        self._selected_path = None
        self._iid_to_file.clear()
        self._iid_to_gidx.clear()
        self._file_to_iid.clear()

        for item in self._tree.get_children():
            self._tree.delete(item)
        self._disable_right_panel()

        has_sha = any(f.sha256 for f in files)
        if has_sha:
            groups = find_duplicates(files)
            method = "SHA-256"
        else:
            groups = find_by_name_size(files)
            method = "имя + размер (SHA-256 не вычислен)"

        self._groups = groups

        if not groups:
            self._stats_label.configure(
                text=f"Дубликатов не найдено среди {len(files)} файлов  •  метод: {method}")
            self._auto_btn.configure(state="disabled")
            self._clear_btn.configure(state="disabled")
            self._delete_btn.configure(state="disabled")
            return

        for g_idx, group in enumerate(groups):
            sha_str = (group.sha256[:24] + "…") if group.sha256 else "—"
            g_text = (f"Группа {g_idx + 1}  •  {group.count} копии  •  "
                      f"+{group.wasted_mb:.1f} МБ  •  SHA: {sha_str}")
            g_iid = self._tree.insert("", "end", text=g_text,
                                      values=("", "", "", ""),
                                      open=True, tags=("tag_group",))
            for f in group.files:
                f_iid = self._tree.insert(
                    g_iid, "end",
                    text=f.name,
                    values=(_MARK_NONE,
                            f"{f.size_mb:.2f}",
                            f.modified.strftime("%Y-%m-%d %H:%M"),
                            f.directory),
                    tags=("tag_plain",),
                )
                self._iid_to_file[f_iid] = f
                self._iid_to_gidx[f_iid] = g_idx
                self._file_to_iid[f.full_path] = f_iid

        total_wasted = sum(g.wasted_mb for g in groups)
        total_files  = sum(g.count     for g in groups)
        self._stats_label.configure(
            text=(f"{len(groups)} групп  •  {total_files} файлов  •  "
                  f"+{total_wasted:.1f} МБ лишних  •  метод: {method}"))
        self._auto_btn.configure(state="normal")
        self._clear_btn.configure(state="normal")
        self._update_delete_btn()

    # ---------------------------------------------------------------- actions

    def _auto_select(self):
        """Keep newest file per group (files[0]), mark the rest for deletion."""
        self._to_delete.clear()
        self._to_keep.clear()
        for group in self._groups:
            if not group.files:
                continue
            self._to_keep.add(group.files[0].full_path)
            for f in group.files[1:]:
                self._to_delete.add(f.full_path)
        self._refresh_all_marks()
        self._update_delete_btn()
        self._update_right_panel_buttons()

    def _clear_marks(self):
        self._to_delete.clear()
        self._to_keep.clear()
        self._refresh_all_marks()
        self._update_delete_btn()
        self._update_right_panel_buttons()

    def _mark_keep(self):
        if not self._selected_path:
            return
        path = self._selected_path
        self._to_delete.discard(path)
        self._to_keep.add(path)
        iid = self._file_to_iid.get(path)
        if iid:
            self._set_row_mark(iid, "keep")
        self._update_delete_btn()
        self._update_right_panel_buttons()

    def _mark_delete(self):
        if not self._selected_path:
            return
        path = self._selected_path
        iid = self._file_to_iid.get(path)
        if iid:
            g_idx = self._iid_to_gidx.get(iid, -1)
            if g_idx >= 0:
                other = [f for f in self._groups[g_idx].files if f.full_path != path]
                if all(f.full_path in self._to_delete for f in other):
                    self._action_label.configure(
                        text="⚠  Нельзя пометить все файлы группы на удаление",
                        text_color="#f0a500")
                    self.after(3500, lambda: self._action_label.configure(
                        text="", text_color="gray60"))
                    return
        self._to_keep.discard(path)
        self._to_delete.add(path)
        if iid:
            self._set_row_mark(iid, "delete")
        self._update_delete_btn()
        self._update_right_panel_buttons()

    def _delete_marked(self):
        if not self._to_delete:
            return
        paths = sorted(self._to_delete)

        total_mb = sum(
            self._iid_to_file[self._file_to_iid[p]].size_mb
            for p in paths
            if p in self._file_to_iid and self._file_to_iid[p] in self._iid_to_file
        )

        MAX_LIST = 8
        lines = [f"  • {Path(p).name}  [{Path(p).parent}]" for p in paths[:MAX_LIST]]
        if len(paths) > MAX_LIST:
            lines.append(f"  … и ещё {len(paths) - MAX_LIST} файлов")
        msg = (f"Будет перемещено в Корзину {len(paths)} файлов "
               f"({total_mb:.1f} МБ):\n\n"
               + "\n".join(lines) + "\n\nПродолжить?")

        if not messagebox.askyesno("Подтверждение удаления", msg, icon="warning"):
            return

        deleted, failed = [], []
        for p in paths:
            try:
                _send_to_trash(p)
                deleted.append(p)
            except Exception as e:
                failed.append((p, str(e)))

        for p in deleted:
            self._to_delete.discard(p)
            iid = self._file_to_iid.pop(p, None)
            if iid:
                self._iid_to_file.pop(iid, None)
                self._iid_to_gidx.pop(iid, None)
                if self._tree.exists(iid):
                    self._tree.delete(iid)

        self._cleanup_empty_groups()
        self._selected_path = None
        self._disable_right_panel()
        self._update_delete_btn()

        status = f"Удалено: {len(deleted)} файлов."
        if failed:
            status += f"  Ошибок: {len(failed)}."
            err_text = "\n".join(f"• {Path(p).name}: {e}" for p, e in failed[:5])
            messagebox.showerror("Ошибки при удалении",
                                 f"Не удалось переместить {len(failed)} файлов:\n\n{err_text}")
        self._action_label.configure(text=status, text_color="gray60")

    def _cleanup_empty_groups(self):
        for g_iid in list(self._tree.get_children()):
            children = self._tree.get_children(g_iid)
            if len(children) <= 1:
                for c in children:
                    f = self._iid_to_file.pop(c, None)
                    self._iid_to_gidx.pop(c, None)
                    if f:
                        self._file_to_iid.pop(f.full_path, None)
                self._tree.delete(g_iid)

        remaining = len(self._tree.get_children())
        if remaining == 0:
            self._stats_label.configure(text="Все дубликаты обработаны!")
            self._auto_btn.configure(state="disabled")
            self._clear_btn.configure(state="disabled")
        else:
            rem_files = sum(len(self._tree.get_children(g))
                            for g in self._tree.get_children())
            self._stats_label.configure(
                text=f"Осталось: {remaining} групп  •  {rem_files} файлов")

    # ---------------------------------------------------------------- tree helpers

    def _refresh_all_marks(self):
        for path, iid in self._file_to_iid.items():
            if path in self._to_delete:
                self._set_row_mark(iid, "delete")
            elif path in self._to_keep:
                self._set_row_mark(iid, "keep")
            else:
                self._set_row_mark(iid, "plain")

    def _set_row_mark(self, iid: str, state: str):
        cur = self._tree.item(iid, "values")
        mark = {
            "delete": _MARK_DELETE,
            "keep":   _MARK_KEEP,
        }.get(state, _MARK_NONE)
        tag = {
            "delete": "tag_delete",
            "keep":   "tag_keep",
        }.get(state, "tag_plain")
        self._tree.item(iid, values=(mark, *cur[1:]), tags=(tag,))

    def _update_delete_btn(self):
        count = len(self._to_delete)
        if count:
            mb = sum(
                self._iid_to_file[self._file_to_iid[p]].size_mb
                for p in self._to_delete
                if p in self._file_to_iid and self._file_to_iid[p] in self._iid_to_file
            )
            self._delete_btn.configure(state="normal")
            self._action_label.configure(
                text=f"Отмечено: {count} файлов  •  {mb:.1f} МБ",
                text_color="#f0a500")
        else:
            self._delete_btn.configure(state="disabled")
            self._action_label.configure(text="", text_color="gray60")

    # ---------------------------------------------------------------- selection

    def _on_select(self, _event):
        sel = self._tree.selection()
        if not sel:
            self._selected_path = None
            self._disable_right_panel()
            return
        iid = sel[0]
        f = self._iid_to_file.get(iid)
        if f is None:  # group row selected
            self._selected_path = None
            self._disable_right_panel()
            return

        self._selected_path = f.full_path
        g_idx = self._iid_to_gidx.get(iid, -1)
        group = self._groups[g_idx] if 0 <= g_idx < len(self._groups) else None

        self._rp_name.configure(text=f.name)
        self._rp_path.configure(text=f.directory)
        sha_line = f"\nSHA: {f.sha256[:32]}…" if f.sha256 else ""
        self._rp_info.configure(
            text=f"{f.size_mb:.2f} МБ  •  {f.modified.strftime('%Y-%m-%d %H:%M')}{sha_line}")
        if group:
            self._rp_group.configure(
                text=f"{group.count} копии  •  +{group.wasted_mb:.1f} МБ лишних")

        for btn in (self._open_btn, self._folder_btn, self._copy_btn,
                    self._keep_btn, self._del_btn):
            btn.configure(state="normal")
        self._update_right_panel_buttons()

    def _update_right_panel_buttons(self):
        if not self._selected_path:
            return
        path = self._selected_path
        if path in self._to_delete:
            self._keep_btn.configure(fg_color="#1a6b3a", hover_color="#145530")
            self._del_btn.configure(fg_color="gray35",   hover_color="gray28")
        elif path in self._to_keep:
            self._keep_btn.configure(fg_color="gray35",   hover_color="gray28")
            self._del_btn.configure(fg_color="#4a1a1a",  hover_color="#3a1010")
        else:
            self._keep_btn.configure(fg_color="#1a4a1a", hover_color="#153815")
            self._del_btn.configure(fg_color="#4a1a1a",  hover_color="#3a1010")

    def _disable_right_panel(self):
        self._rp_name.configure(text="—")
        self._rp_path.configure(text="")
        self._rp_info.configure(text="")
        self._rp_group.configure(text="—")
        for btn in (self._open_btn, self._folder_btn, self._copy_btn,
                    self._keep_btn, self._del_btn):
            btn.configure(state="disabled")

    # ---------------------------------------------------------------- events

    def _on_double_click(self, event):
        item = self._tree.identify_row(event.y)
        if item and item in self._iid_to_file:
            self._open_file()

    def _on_right_click(self, event):
        item = self._tree.identify_row(event.y)
        if item and item in self._iid_to_file:
            self._tree.selection_set(item)
            self._ctx_menu.post(event.x_root, event.y_root)

    # ---------------------------------------------------------------- file actions

    def _open_file(self):
        if self._selected_path:
            try:
                os.startfile(self._selected_path)
            except Exception:
                pass

    def _open_folder(self):
        if self._selected_path:
            try:
                subprocess.Popen(
                    f'explorer /select,"{os.path.normpath(self._selected_path)}"')
            except Exception:
                pass

    def _copy_path(self):
        if self._selected_path:
            self.clipboard_clear()
            self.clipboard_append(self._selected_path)
