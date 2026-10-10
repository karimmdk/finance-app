#!/usr/bin/env python3
"""کد بک‌اند (app/)، migrations/ و static/ را به پروژه اندروید کپی می‌کند.
هر بار قبل از ساخت APK (یا بعد از تغییر کد اپ) یک‌بار اجرا کنید:  python android/sync_backend.py
"""
import glob
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

WIDTHS_KEY = "finance-app:transactions-column-widths"

# تغییر کوچک در bundle «کپی اندروید»: عرض ستون‌های جدول تراکنش (که کاربر با کشیدن عوض می‌کند) ذخیره و برگردانده شود.
BUNDLE_PATCHES = [
    (
        "[is,ad]=j.useState(()=>Object.fromEntries(Ti.map(f=>[f.key,f.width])))",
        "[is,ad]=j.useState(()=>{const d=Object.fromEntries(Ti.map(f=>[f.key,f.width]));"
        "try{const s=JSON.parse(localStorage.getItem(\"" + WIDTHS_KEY + "\")||\"{}\");"
        "for(const k in s)if(k in d&&Number.isFinite(s[k])&&s[k]>=50)d[k]=s[k]}catch{}return d})",
    ),
    (
        "localStorage.setItem(Uo,JSON.stringify(Ur))}catch{}},[Ur]);",
        "localStorage.setItem(Uo,JSON.stringify(Ur))}catch{}},[Ur]);"
        "j.useEffect(()=>{try{localStorage.setItem(\"" + WIDTHS_KEY + "\",JSON.stringify(is))}catch{}},[is]);",
    ),
]


def patch_bundle(static_dst: Path):
    bundles = glob.glob(str(static_dst / "assets" / "index-*.js"))
    assert len(bundles) == 1, f"expected one index-*.js bundle, found {len(bundles)}"
    path = Path(bundles[0])
    code = path.read_text(encoding="utf-8")
    for old, new in BUNDLE_PATCHES:
        if code.count(old) != 1:
            # فرانت‌اند عوض شده؛ بیلد خراب نشود، فقط این قابلیت (ذخیره عرض ستون‌ها) غیرفعال می‌ماند
            print(f"  WARNING: bundle patch skipped (anchor not found once): {old[:50]}...")
            continue
        code = code.replace(old, new)
    path.write_text(code, encoding="utf-8")
    print(f"  + column-width persistence patch -> {path.name}")


def add_mobile_ui(static_dst: Path):
    """CSS/JS مخصوص گوشی را فقط به «کپی اندروید» static اضافه کن (static/ دسکتاپ دست‌نخورده می‌ماند)."""
    src = ROOT / "android" / "mobile"
    names = ("mobile.css", "mobile.js", "extras.js")
    blob = b""
    for name in names:
        data = (src / name).read_bytes()
        (static_dst / "assets" / name).write_bytes(data)
        blob += data
    ver = hashlib.md5(blob).hexdigest()[:8]
    index = static_dst / "index.html"
    html = index.read_text(encoding="utf-8")
    tags = (f'    <link rel="stylesheet" href="/assets/mobile.css?v={ver}">\n'
            f'    <script defer src="/assets/mobile.js?v={ver}"></script>\n'
            f'    <script defer src="/assets/extras.js?v={ver}"></script>\n  ')
    assert "</head>" in html
    index.write_text(html.replace("</head>", tags + "</head>", 1), encoding="utf-8")
    print(f"  + mobile UI (v={ver}) -> {static_dst.relative_to(ROOT)}")
    patch_bundle(static_dst)


print("Syncing backend into Android project...")
sync(ROOT / "app", MAIN / "python" / "app")
sync(ROOT / "migrations", MAIN / "assets" / "payload" / "migrations")
sync(ROOT / "static", MAIN / "assets" / "payload" / "static")
add_mobile_ui(MAIN / "assets" / "payload" / "static")
print("Done.")
