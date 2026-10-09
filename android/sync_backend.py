#!/usr/bin/env python3
"""کد بک‌اند (app/)، migrations/ و static/ را به پروژه اندروید کپی می‌کند.
هر بار قبل از ساخت APK (یا بعد از تغییر کد اپ) یک‌بار اجرا کنید:  python android/sync_backend.py
"""
import hashlib
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

def add_mobile_ui(static_dst: Path):
    """CSS/JS مخصوص گوشی را فقط به «کپی اندروید» static اضافه کن (static/ دسکتاپ دست‌نخورده می‌ماند)."""
    src = ROOT / "android" / "mobile"
    css, js = (src / "mobile.css").read_bytes(), (src / "mobile.js").read_bytes()
    (static_dst / "assets" / "mobile.css").write_bytes(css)
    (static_dst / "assets" / "mobile.js").write_bytes(js)
    ver = hashlib.md5(css + js).hexdigest()[:8]
    index = static_dst / "index.html"
    html = index.read_text(encoding="utf-8")
    tags = (f'    <link rel="stylesheet" href="/assets/mobile.css?v={ver}">\n'
            f'    <script defer src="/assets/mobile.js?v={ver}"></script>\n  ')
    assert "</head>" in html
    index.write_text(html.replace("</head>", tags + "</head>", 1), encoding="utf-8")
    print(f"  + mobile UI (v={ver}) -> {static_dst.relative_to(ROOT)}")


print("Syncing backend into Android project...")
sync(ROOT / "app", MAIN / "python" / "app")
sync(ROOT / "migrations", MAIN / "assets" / "payload" / "migrations")
sync(ROOT / "static", MAIN / "assets" / "payload" / "static")
add_mobile_ui(MAIN / "assets" / "payload" / "static")
print("Done.")
