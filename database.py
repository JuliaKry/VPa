import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable


STATUS_PENDING = "Ожидает"
STATUS_DONE = "Готово"
STATUS_OVERDUE = "Просрочено"
STATUS_CANCELLED = "Отменено"

STATUSES = (STATUS_PENDING, STATUS_DONE, STATUS_OVERDUE, STATUS_CANCELLED)

DATETIME_FORMAT = "%Y-%m-%d %H:%M"


class ReminderDB:
    def __init__(self, db_path: str | Path = "reminders.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                trigger_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Ожидает'
                    CHECK(status IN ('Ожидает', 'Готово', 'Просрочено', 'Отменено')),
                notified_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        self.connection.commit()

    def add_reminder(self, title: str, description: str, trigger_at: datetime) -> int:
        now = self._now_iso()
        cursor = self.connection.execute(
            """
            INSERT INTO reminders (title, description, trigger_at, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                title.strip(),
                description.strip(),
                self._to_storage(trigger_at),
                STATUS_PENDING,
                now,
                now,
            ),
        )
        self.connection.commit()
        return int(cursor.lastrowid)

    def delete_reminder(self, reminder_id: int) -> None:
        self.connection.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        self.connection.commit()

    def set_status(self, reminder_id: int, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"Unknown reminder status: {status}")

        self.connection.execute(
            """
            UPDATE reminders
            SET status = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, self._now_iso(), reminder_id),
        )
        self.connection.commit()

    def mark_notified(self, reminder_id: int) -> None:
        self.connection.execute(
            """
            UPDATE reminders
            SET notified_at = COALESCE(notified_at, ?), updated_at = ?
            WHERE id = ?
            """,
            (self._now_iso(), self._now_iso(), reminder_id),
        )
        self.connection.commit()

    def list_reminders(self, status: str | None = None) -> list[sqlite3.Row]:
        if status and status != "Все":
            cursor = self.connection.execute(
                """
                SELECT *
                FROM reminders
                WHERE status = ?
                ORDER BY trigger_at ASC, id ASC
                """,
                (status,),
            )
        else:
            cursor = self.connection.execute(
                """
                SELECT *
                FROM reminders
                ORDER BY trigger_at ASC, id ASC
                """
            )
        return list(cursor.fetchall())

    def due_reminders(self, now: datetime | None = None) -> list[sqlite3.Row]:
        moment = self._to_storage(now or datetime.now())
        cursor = self.connection.execute(
            """
            SELECT *
            FROM reminders
            WHERE status = ?
              AND notified_at IS NULL
              AND trigger_at <= ?
            ORDER BY trigger_at ASC, id ASC
            """,
            (STATUS_PENDING, moment),
        )
        return list(cursor.fetchall())

    def mark_notified_pending_as_overdue(self) -> int:
        cursor = self.connection.execute(
            """
            UPDATE reminders
            SET status = ?, updated_at = ?
            WHERE status = ?
              AND notified_at IS NOT NULL
            """,
            (STATUS_OVERDUE, self._now_iso(), STATUS_PENDING),
        )
        self.connection.commit()
        return int(cursor.rowcount)

    def update_overdue(self, now: datetime | None = None) -> int:
        moment = self._to_storage(now or datetime.now())
        cursor = self.connection.execute(
            """
            UPDATE reminders
            SET status = ?, updated_at = ?
            WHERE status = ?
              AND notified_at IS NOT NULL
              AND trigger_at < ?
            """,
            (STATUS_OVERDUE, self._now_iso(), STATUS_PENDING, moment),
        )
        self.connection.commit()
        return int(cursor.rowcount)

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def parse_user_datetime(value: str) -> datetime:
        return datetime.strptime(value.strip(), DATETIME_FORMAT)

    @staticmethod
    def format_user_datetime(value: str) -> str:
        return datetime.strptime(value, DATETIME_FORMAT).strftime(DATETIME_FORMAT)

    @staticmethod
    def _to_storage(value: datetime) -> str:
        return value.strftime(DATETIME_FORMAT)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def statuses_for_filter() -> Iterable[str]:
    return ("Все", *STATUSES)
