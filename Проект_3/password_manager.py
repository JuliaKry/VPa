import argparse
import getpass
import hashlib
import secrets
import sqlite3
import string
from pathlib import Path
from typing import Any


DB_PATH = Path("passwords.sqlite3")
KEY_PATH = Path(".key")


# -------------------------
# Database functions
# -------------------------


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS master_password (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                password_hash TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS passwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL UNIQUE,
                login TEXT NOT NULL,
                password_encrypted TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def get_master_hash() -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT password_hash FROM master_password WHERE id = 1"
        ).fetchone()
    return row[0] if row else None


def save_master_hash(password_hash: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO master_password (id, password_hash)
            VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET password_hash = excluded.password_hash
            """,
            (password_hash,),
        )


def add_password_record(title: str, login: str, encrypted_password: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO passwords (title, login, password_encrypted)
            VALUES (?, ?, ?)
            """,
            (title, login, encrypted_password),
        )


def get_password_record(title: str) -> tuple[str, str] | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT login, password_encrypted
            FROM passwords
            WHERE title = ?
            """,
            (title,),
        ).fetchone()
    return row if row else None


def list_password_records() -> list[tuple[str, str]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT title, login
            FROM passwords
            ORDER BY title COLLATE NOCASE
            """
        ).fetchall()
    return rows


def delete_password_record(title: str) -> int:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM passwords WHERE title = ?", (title,))
    return cursor.rowcount


# -------------------------
# Encryption functions
# -------------------------


def get_fernet_class() -> Any:
    try:
        from cryptography.fernet import Fernet
    except ModuleNotFoundError as error:
        raise SystemExit(
            "Библиотека cryptography не установлена. "
            "Установите зависимости командой: pip install -r requirements.txt"
        ) from error

    return Fernet


def load_or_create_key(key_path: Path = KEY_PATH) -> bytes:
    Fernet = get_fernet_class()

    if key_path.exists():
        return key_path.read_bytes()

    key = Fernet.generate_key()
    key_path.write_bytes(key)
    key_path.chmod(0o600)
    return key


def get_cipher() -> Any:
    Fernet = get_fernet_class()
    return Fernet(load_or_create_key())


def encrypt_password(password: str) -> str:
    return get_cipher().encrypt(password.encode("utf-8")).decode("utf-8")


def decrypt_password(encrypted_password: str) -> str:
    return get_cipher().decrypt(encrypted_password.encode("utf-8")).decode("utf-8")


# -------------------------
# Authentication functions
# -------------------------


def sha256_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def setup_master_password() -> None:
    while True:
        password = getpass.getpass("Создайте мастер-пароль: ")
        password_repeat = getpass.getpass("Повторите мастер-пароль: ")

        if not password:
            print("Мастер-пароль не может быть пустым.")
            continue

        if password != password_repeat:
            print("Пароли не совпадают. Попробуйте снова.")
            continue

        save_master_hash(sha256_hash(password))
        print("Мастер-пароль создан.")
        return


def authenticate() -> None:
    stored_hash = get_master_hash()
    if stored_hash is None:
        setup_master_password()
        return

    password = getpass.getpass("Введите мастер-пароль: ")
    if sha256_hash(password) != stored_hash:
        raise SystemExit("Неверный мастер-пароль.")


# -------------------------
# CLI command handlers
# -------------------------


def prompt_if_missing(value: str | None, prompt: str) -> str:
    if value:
        return value
    return input(prompt).strip()


def handle_add(args: argparse.Namespace) -> None:
    title = prompt_if_missing(args.title, "Название/откуда: ")
    login = prompt_if_missing(args.login, "Логин: ")
    password = args.password or getpass.getpass("Пароль для сохранения: ")

    if not title or not login or not password:
        raise SystemExit("Название, логин и пароль обязательны.")

    try:
        add_password_record(title, login, encrypt_password(password))
    except sqlite3.IntegrityError:
        raise SystemExit(f'Запись "{title}" уже существует.')

    print(f'Запись "{title}" добавлена.')


def handle_get(args: argparse.Namespace) -> None:
    title = prompt_if_missing(args.title, "Название/откуда: ")
    record = get_password_record(title)

    if record is None:
        raise SystemExit(f'Запись "{title}" не найдена.')

    login, encrypted_password = record
    print(f"Название: {title}")
    print(f"Логин: {login}")
    print(f"Пароль: {decrypt_password(encrypted_password)}")


def handle_list(_: argparse.Namespace) -> None:
    records = list_password_records()

    if not records:
        print("Сохранённых записей нет.")
        return

    for title, login in records:
        print(f"{title}: {login}")


def handle_delete(args: argparse.Namespace) -> None:
    title = prompt_if_missing(args.title, "Название/откуда: ")
    deleted_count = delete_password_record(title)

    if deleted_count == 0:
        raise SystemExit(f'Запись "{title}" не найдена.')

    print(f'Запись "{title}" удалена.')


def generate_password(length: int = 16) -> str:
    if length < 8:
        raise ValueError("Длина пароля должна быть не меньше 8 символов.")

    alphabet = string.ascii_letters + string.digits + string.punctuation
    return "".join(secrets.choice(alphabet) for _ in range(length))


def handle_new(args: argparse.Namespace) -> None:
    title = prompt_if_missing(args.title, "Название/откуда: ")
    login = prompt_if_missing(args.login, "Логин: ")

    try:
        password = generate_password(args.length)
    except ValueError as error:
        raise SystemExit(str(error))

    if not title or not login:
        raise SystemExit("Название и логин обязательны.")

    try:
        add_password_record(title, login, encrypt_password(password))
    except sqlite3.IntegrityError:
        raise SystemExit(f'Запись "{title}" уже существует.')

    print(f'Запись "{title}" добавлена.')
    print(f"Сгенерированный пароль: {password}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI-менеджер паролей с SQLite3 и Fernet-шифрованием."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Добавить новую запись")
    add_parser.add_argument("-t", "--title", help="Название/откуда")
    add_parser.add_argument("-l", "--login", help="Логин")
    add_parser.add_argument("-p", "--password", help="Пароль для сохранения")
    add_parser.set_defaults(handler=handle_add)

    get_parser = subparsers.add_parser("get", help="Получить пароль по названию")
    get_parser.add_argument("title", nargs="?", help="Название/откуда")
    get_parser.set_defaults(handler=handle_get)

    list_parser = subparsers.add_parser("list", help="Показать все записи")
    list_parser.set_defaults(handler=handle_list)

    delete_parser = subparsers.add_parser("delete", help="Удалить запись по названию")
    delete_parser.add_argument("title", nargs="?", help="Название/откуда")
    delete_parser.set_defaults(handler=handle_delete)

    new_parser = subparsers.add_parser(
        "new", help="Создать и сохранить новый сгенерированный пароль"
    )
    new_parser.add_argument("-t", "--title", help="Название/откуда")
    new_parser.add_argument("-l", "--login", help="Логин")
    new_parser.add_argument(
        "--length",
        type=int,
        default=16,
        help="Длина генерируемого пароля (по умолчанию: 16)",
    )
    new_parser.set_defaults(handler=handle_new)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    init_db()
    load_or_create_key()
    authenticate()
    args.handler(args)


if __name__ == "__main__":
    main()
