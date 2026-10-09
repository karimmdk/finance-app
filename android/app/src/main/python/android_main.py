"""
نقطه ورود نسخه اندروید: سرور FastAPI را داخل خود گوشی روی 127.0.0.1 بالا می‌آورد.
Kotlin این تابع را با Chaquopy صدا می‌زند و [port, token, db_dir, warning] را می‌گیرد.

- دیتابیس (finance.db) و attachments داخل پوشه db_dir (پوشه قابل‌سینک کاربر) نگه داشته می‌شود.
- journal_mode = DELETE: فقط یک فایل finance.db هست و بعد از هر commit کامل است (بدون -wal/-shm).
- امنیت: هر درخواست باید کوکی fa_token (توکن تصادفی همین اجرا) داشته باشد.
"""
import hmac
import os
import secrets
import shutil
import socket
import sqlite3
import threading
from pathlib import Path

_started = None  # [port, token, db_dir, warning]
_db = None


class TokenGate:
    def __init__(self, app, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            cookie = dict(scope["headers"]).get(b"cookie", b"").decode("latin-1")
            ok = any(
                part.strip().startswith("fa_token=")
                and hmac.compare_digest(part.strip()[len("fa_token="):], self.token)
                for part in cookie.split(";")
            )
            if not ok:
                if scope["type"] == "http":
                    await send({"type": "http.response.start", "status": 403,
                                "headers": [(b"content-type", b"text/plain")]})
                    await send({"type": "http.response.body", "body": b"Forbidden"})
                else:
                    await send({"type": "websocket.close", "code": 1008})
                return
        await self.app(scope, receive, send)


def _probe_writable(d: Path) -> None:
    """مطمئن شو SQLite واقعاً می‌تواند داخل این پوشه بنویسد (روی حافظه مشترک گاهی قفل‌کردن فایل مشکل دارد)."""
    d.mkdir(parents=True, exist_ok=True)
    probe = d / ".fa_probe.db"
    for suffix in ("", "-journal"):
        Path(str(probe) + suffix).unlink(missing_ok=True)
    try:
        c = sqlite3.connect(str(probe))
        c.execute("PRAGMA journal_mode = DELETE")
        c.execute("CREATE TABLE t (x)")
        c.execute("INSERT INTO t VALUES (1)")
        c.commit()
        c.close()
    finally:
        for suffix in ("", "-journal"):
            Path(str(probe) + suffix).unlink(missing_ok=True)


def _migrate_legacy(private: Path, target: Path) -> None:
    """نسخه قبلی برنامه دیتابیس را در حافظه خصوصی نگه می‌داشت؛ اگر پوشه جدید خالی است، آن را منتقل کن."""
    old_db, new_db = private / "finance.db", target / "finance.db"
    if target == private or new_db.exists() or not old_db.exists():
        return
    src = sqlite3.connect(str(old_db))
    dst = sqlite3.connect(str(new_db))
    try:
        src.backup(dst)  # WAL را هم درست در نظر می‌گیرد
    finally:
        dst.close()
        src.close()
    old_att = private / "attachments"
    if old_att.exists():
        shutil.copytree(old_att, target / "attachments", dirs_exist_ok=True)


def _apply_pending_restore(private: Path, target: Path) -> None:
    """اگر کاربر فایل بکاپ انتخاب کرده بود، قبل از باز شدن دیتابیس جایگزینش کن."""
    pending = private / "restore_pending.db"
    if not pending.exists():
        return
    db = target / "finance.db"
    for suffix in ("", "-wal", "-shm", "-journal"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    shutil.copyfile(pending, db)  # (replace بین دو حافظه متفاوت کار نمی‌کند)
    pending.unlink()


def flush() -> bool:
    """همه تغییرات را داخل فایل finance.db ثبت کن (قبل از رفتن برنامه به پس‌زمینه/خروج)."""
    if _db is None:
        return False
    try:
        _db.commit()
        _db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return True
    except Exception:
        return False


def start(files_dir: str, payload_dir: str, db_dir: str = "", preferred_port: int = 47831):
    global _started, _db
    if _started:
        return list(_started)

    files = Path(files_dir)
    payload = Path(payload_dir)
    private = files / "data"
    private.mkdir(parents=True, exist_ok=True)

    warning = ""
    target = Path(db_dir) if db_dir else private
    try:
        _probe_writable(target)
    except Exception as e:  # پوشه قابل‌نوشتن نیست یا SQLite آنجا کار نمی‌کند → حافظه خصوصی
        warning = f"{type(e).__name__}: {e}"
        target = private
        _probe_writable(target)

    _migrate_legacy(private, target)
    _apply_pending_restore(private, target)

    os.environ["FINANCE_DB_PATH"] = str(target / "finance.db")
    os.environ["FINANCE_ATTACHMENTS_DIR"] = str(target / "attachments")
    os.environ["FINANCE_STATIC_DIR"] = str(payload / "static")
    os.environ["FINANCE_MIGRATIONS_DIR"] = str(payload / "migrations")
    os.environ["FINANCE_JOURNAL_MODE"] = "DELETE"

    import pydantic_compat  # noqa: F401  (قبل از import شدن app)
    import uvicorn
    from app.db import open_db
    from app.main import create_app

    db_path = os.environ["FINANCE_DB_PATH"]
    _db = open_db(db_path)
    app = create_app(_db, static_dir=os.environ["FINANCE_STATIC_DIR"], db_path=db_path)

    token = secrets.token_urlsafe(32)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", preferred_port))
    except OSError:
        sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    config = uvicorn.Config(TokenGate(app, token), log_level="warning",
                            loop="asyncio", http="h11", lifespan="off")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, kwargs={"sockets": [sock]},
                     daemon=True, name="finance-server").start()

    _started = [port, token, str(target), warning]
    return list(_started)
