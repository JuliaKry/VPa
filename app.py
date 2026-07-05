import os
import subprocess
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from database import (
    DATETIME_FORMAT,
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_OVERDUE,
    STATUS_PENDING,
    ReminderDB,
    statuses_for_filter,
)


CHECK_INTERVAL_MS = 5_000


class ReminderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Напоминалка")
        self.root.geometry("920x620")
        self.root.minsize(820, 540)

        self.db = ReminderDB()
        self.status_filter = tk.StringVar(value="Все")
        self.title_var = tk.StringVar()
        self.trigger_at_var = tk.StringVar(
            value=(datetime.now() + timedelta(minutes=10)).strftime(DATETIME_FORMAT)
        )

        self._build_ui()
        self.refresh_reminders()
        self.check_notifications()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        form = ttk.LabelFrame(main, text="Новое напоминание", padding=10)
        form.pack(fill=tk.X)

        ttk.Label(form, text="Заголовок").grid(row=0, column=0, sticky=tk.W)
        title_entry = ttk.Entry(form, textvariable=self.title_var)
        title_entry.grid(row=0, column=1, sticky=tk.EW, padx=(8, 0))

        ttk.Label(form, text="Дата и время").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        datetime_entry = ttk.Entry(form, textvariable=self.trigger_at_var)
        datetime_entry.grid(row=1, column=1, sticky=tk.EW, padx=(8, 0), pady=(8, 0))
        ttk.Label(form, text=f"Формат: {DATETIME_FORMAT}").grid(
            row=1, column=2, sticky=tk.W, padx=(8, 0), pady=(8, 0)
        )

        ttk.Label(form, text="Описание").grid(row=2, column=0, sticky=tk.NW, pady=(8, 0))
        self.description_text = tk.Text(form, height=4, wrap=tk.WORD)
        self.description_text.grid(
            row=2, column=1, columnspan=2, sticky=tk.EW, padx=(8, 0), pady=(8, 0)
        )

        add_button = ttk.Button(form, text="Добавить", command=self.add_reminder)
        add_button.grid(row=3, column=1, sticky=tk.E, pady=(10, 0))

        form.columnconfigure(1, weight=1)

        toolbar = ttk.Frame(main)
        toolbar.pack(fill=tk.X, pady=(12, 8))

        ttk.Label(toolbar, text="Фильтр по статусу:").pack(side=tk.LEFT)
        filter_box = ttk.Combobox(
            toolbar,
            textvariable=self.status_filter,
            values=list(statuses_for_filter()),
            state="readonly",
            width=18,
        )
        filter_box.pack(side=tk.LEFT, padx=(8, 12))
        filter_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_reminders())

        ttk.Button(toolbar, text="Обновить", command=self.refresh_reminders).pack(side=tk.LEFT)
        ttk.Button(toolbar, text='Отметить "Готово"', command=self.mark_done).pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        ttk.Button(toolbar, text='Отметить "Отменено"', command=self.mark_cancelled).pack(
            side=tk.RIGHT, padx=(8, 0)
        )
        ttk.Button(toolbar, text="Удалить", command=self.delete_selected).pack(side=tk.RIGHT)

        columns = ("id", "title", "description", "trigger_at", "status")
        self.tree = ttk.Treeview(main, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("id", text="ID")
        self.tree.heading("title", text="Заголовок")
        self.tree.heading("description", text="Описание")
        self.tree.heading("trigger_at", text="Дата и время")
        self.tree.heading("status", text="Статус")

        self.tree.column("id", width=60, anchor=tk.CENTER)
        self.tree.column("title", width=190)
        self.tree.column("description", width=330)
        self.tree.column("trigger_at", width=150, anchor=tk.CENTER)
        self.tree.column("status", width=120, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(main, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        title_entry.focus_set()

    def add_reminder(self) -> None:
        title = self.title_var.get().strip()
        description = self.description_text.get("1.0", tk.END).strip()
        trigger_at_raw = self.trigger_at_var.get().strip()

        if not title:
            messagebox.showwarning("Проверьте данные", "Введите заголовок напоминания.")
            return

        try:
            trigger_at = ReminderDB.parse_user_datetime(trigger_at_raw)
        except ValueError:
            messagebox.showerror(
                "Неверная дата",
                f"Введите дату и время в формате {DATETIME_FORMAT}, например 2026-07-05 14:30.",
            )
            return

        self.db.add_reminder(title, description, trigger_at)
        self.title_var.set("")
        self.description_text.delete("1.0", tk.END)
        self.trigger_at_var.set((datetime.now() + timedelta(minutes=10)).strftime(DATETIME_FORMAT))
        self.refresh_reminders()

    def refresh_reminders(self) -> None:
        self.db.update_overdue()

        for item in self.tree.get_children():
            self.tree.delete(item)

        for reminder in self.db.list_reminders(self.status_filter.get()):
            self.tree.insert(
                "",
                tk.END,
                values=(
                    reminder["id"],
                    reminder["title"],
                    reminder["description"],
                    reminder["trigger_at"],
                    reminder["status"],
                ),
            )

    def delete_selected(self) -> None:
        reminder_id = self._selected_reminder_id()
        if reminder_id is None:
            return

        if messagebox.askyesno("Удалить напоминание", "Удалить выбранное напоминание?"):
            self.db.delete_reminder(reminder_id)
            self.refresh_reminders()

    def mark_done(self) -> None:
        self._set_selected_status(STATUS_DONE)

    def mark_cancelled(self) -> None:
        self._set_selected_status(STATUS_CANCELLED)

    def _set_selected_status(self, status: str) -> None:
        reminder_id = self._selected_reminder_id()
        if reminder_id is None:
            return

        self.db.set_status(reminder_id, status)
        self.refresh_reminders()

    def _selected_reminder_id(self) -> int | None:
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Нет выбора", "Выберите напоминание в списке.")
            return None

        values = self.tree.item(selected[0], "values")
        return int(values[0])

    def check_notifications(self) -> None:
        due_reminders = self.db.due_reminders()
        for index, reminder in enumerate(due_reminders):
            self.db.mark_notified(reminder["id"])
            self.show_popup(reminder, offset=index)

        if due_reminders:
            self.db.mark_notified_pending_as_overdue()
            self.refresh_reminders()

        self.root.after(CHECK_INTERVAL_MS, self.check_notifications)

    def show_popup(self, reminder, offset: int = 0) -> None:
        self._activate_app_best_effort()

        popup = tk.Toplevel(self.root)
        popup.title("Напоминание")
        popup.geometry(f"420x240+{180 + offset * 28}+{140 + offset * 28}")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        popup.lift()
        popup.focus_force()

        container = ttk.Frame(popup, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        ttk.Label(container, text=reminder["title"], font=("TkDefaultFont", 15, "bold")).pack(
            anchor=tk.W
        )
        ttk.Label(container, text=f"Время: {reminder['trigger_at']}").pack(
            anchor=tk.W, pady=(8, 0)
        )

        description = reminder["description"] or "Без описания"
        message = tk.Message(container, text=description, width=370)
        message.pack(anchor=tk.W, fill=tk.X, pady=(12, 0))

        button_row = ttk.Frame(container)
        button_row.pack(side=tk.BOTTOM, fill=tk.X, pady=(16, 0))

        ttk.Button(
            button_row,
            text='Готово',
            command=lambda: self._popup_set_status(popup, reminder["id"], STATUS_DONE),
        ).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(
            button_row,
            text='Отменено',
            command=lambda: self._popup_set_status(popup, reminder["id"], STATUS_CANCELLED),
        ).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(button_row, text="Закрыть", command=popup.destroy).pack(side=tk.RIGHT)

        popup.after(400, lambda: popup.attributes("-topmost", True))

    def _popup_set_status(self, popup: tk.Toplevel, reminder_id: int, status: str) -> None:
        self.db.set_status(reminder_id, status)
        popup.destroy()
        self.refresh_reminders()

    def _activate_app_best_effort(self) -> None:
        # On macOS this helps bring the Tk popup forward; if permissions block it, Tk topmost still works.
        script = (
            'tell application "System Events" to set frontmost of '
            f'(first process whose unix id is {os.getpid()}) to true'
        )
        try:
            subprocess.run(["osascript", "-e", script], check=False, timeout=1)
        except (OSError, subprocess.SubprocessError):
            pass

    def on_close(self) -> None:
        self.db.close()
        self.root.destroy()
