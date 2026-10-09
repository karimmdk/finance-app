#!/usr/bin/env python3
"""کد بک‌اند (app/)، migrations/ و static/ را به پروژه اندروید کپی می‌کند.
هر بار قبل از ساخت APK (یا بعد از تغییر کد اپ) یک‌بار اجرا کنید:  python android/sync_backend.py
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "android" / "app" / "src" / "main"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "{*")

def sync(src: Path, dst: Path):
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=IGNORE)
    print(f"  {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")

print("Syncing backend into Android project...")
sync(ROOT / "app", MAIN / "python" / "app")
sync(ROOT / "migrations", MAIN / "assets" / "payload" / "migrations")
sync(ROOT / "static", MAIN / "assets" / "payload" / "static")
print("Done.")
