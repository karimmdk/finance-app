"""
نقطه ورود واقعی — معادل src/server/index.ts نسخه Node.

نکته مهم ترتیب اجرا: مسیرهای پایه (resource_dir برای فایل‌های فقط‌خواندنی بسته‌بندی‌شده مثل
migrations/static، و writable_dir برای داده کاربر مثل finance.db/attachments) باید قبل از
import شدن app.main محاسبه و به‌عنوان متغیر محیطی ست شوند — چون app/routes/transactions.py
مسیر ATTACHMENTS_DIR را در زمان import ماژول (نه در زمان اجرای main) از env var می‌خواند.
"""
import os
import sys
from pathlib import Path


def _resource_dir() -> Path:
    """محل فایل‌های فقط‌خواندنی بسته‌بندی‌شده (migrations, static) — در PyInstaller: sys._MEIPASS."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


def _writable_dir() -> Path:
    """
    محل داده قابل‌نوشتن کاربر (finance.db, attachments) — کنار خودِ فایل اجرایی، نه داخل
    پوشه فقط‌خواندنی بسته‌بندی (_internal/MEIPASS)، تا با کپی‌کردن کل پوشه، داده هم همراهش بیاید.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_resource = _resource_dir()
_writable = _writable_dir()

def _sync_dir() -> Path | None:
    """
    پوشه داده سینک‌شده (مثلاً پوشه MEGA). از متغیر محیطی FINANCE_DATA_DIR، یا اگر نبود از فایل متنی
    sync_dir.txt کنار برنامه (یک خط: مسیر پوشه) خوانده می‌شود. اگر هیچ‌کدام نبود، رفتار قبلی (data/ کنار برنامه).
    """
    value = os.environ.get("FINANCE_DATA_DIR", "").strip()
    cfg = _writable / "sync_dir.txt"
    if not value and cfg.exists():
        value = cfg.read_text(encoding="utf-8-sig").strip()
    value = value.strip('"').strip("'")
    return Path(value).expanduser() if value else None


_data = _sync_dir()
if _data is not None:
    # حالت سینک: فقط یک فایل finance.db (بدون -wal) تا ابزار سینک نسخه کامل را ببرد
    os.environ.setdefault("FINANCE_JOURNAL_MODE", "DELETE")
else:
    _data = _writable / "data"

os.environ.setdefault("FINANCE_DB_PATH", str(_data / "finance.db"))
os.environ.setdefault("FINANCE_ATTACHMENTS_DIR", str(_data / "attachments"))
os.environ.setdefault("FINANCE_STATIC_DIR", str(_resource / "static"))

# این importها عمداً بعد از تنظیم متغیرهای محیطی بالا هستند
import uvicorn  # noqa: E402
from app.db import open_db  # noqa: E402
from app.main import create_app  # noqa: E402


def main():
    db_path = os.environ["FINANCE_DB_PATH"]
    static_dir = os.environ["FINANCE_STATIC_DIR"]

    db = open_db(db_path)
    app = create_app(db, static_dir=static_dir, db_path=db_path)

    port = int(os.environ.get("PORT", "4000"))
    print(f"Finance API listening on http://localhost:{port}")
    print(f"Database: {db_path}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
