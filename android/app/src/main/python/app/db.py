"""
اتصال SQLite و اجرای migrationها — معادل src/db/index.ts نسخه Node.
از ماژول استاندارد sqlite3 پایتون استفاده می‌شود (بدون هیچ وابستگی native خارجی)،
که دقیقاً همان چیزی است که بسته‌بندی یک فایل قابل‌حمل تک‌پوشه‌ای را با PyInstaller
قابل‌اعتماد می‌کند (بر خلاف better-sqlite3 در نسخه Node که یک native addon است).
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager


def _migrations_dir() -> Path:
    # وقتی با PyInstaller بسته‌بندی شود، فایل‌های داده در sys._MEIPASS قرار می‌گیرند
    import os, sys
    if os.environ.get("FINANCE_MIGRATIONS_DIR"):  # اندروید: migrationها از assets کپی می‌شوند
        return Path(os.environ["FINANCE_MIGRATIONS_DIR"])
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "migrations"
    return Path(__file__).resolve().parent.parent / "migrations"


def open_db(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # پیش‌فرض WAL؛ برای پوشه‌های سینک‌شده (MEGA/Dropbox/…) باید DELETE باشد تا فقط یک فایل .db
    # وجود داشته باشد و بعد از هر commit کامل و مستقل باشد (بدون -wal/-shm).
    import os
    mode = os.environ.get("FINANCE_JOURNAL_MODE", "WAL").upper()
    if mode not in ("WAL", "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "OFF"):
        mode = "WAL"
    conn.execute(f"PRAGMA journal_mode = {mode}")
    conn.execute("PRAGMA foreign_keys = ON")
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT (datetime('now')))"
    )
    conn.commit()

    applied = {row["filename"] for row in conn.execute("SELECT filename FROM schema_migrations")}
    migrations_dir = _migrations_dir()
    for path in sorted(migrations_dir.glob("*.sql")):
        if path.name in applied:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.executescript(sql)
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


@contextmanager
def transaction(conn: sqlite3.Connection):
    """Context manager برای گروه‌بندی چند عملیات در یک تراکنش اتمیک (معادل db.transaction در better-sqlite3)."""
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
