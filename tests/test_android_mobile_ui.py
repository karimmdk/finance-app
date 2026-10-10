"""اصلاحات نمایش موبایل فقط باید در «کپی اندروید» static باشد؛ static/ دسکتاپ دست‌نخورده بماند."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAYLOAD = ROOT / "android" / "app" / "src" / "main" / "assets" / "payload" / "static"


def test_mobile_ui_is_injected_only_into_android_copy():
    subprocess.run([sys.executable, str(ROOT / "android" / "sync_backend.py")], check=True, capture_output=True)

    android_index = (PAYLOAD / "index.html").read_text(encoding="utf-8")
    assert "/assets/mobile.css?v=" in android_index
    assert "/assets/mobile.js?v=" in android_index
    assert "/assets/extras.js?v=" in android_index
    assert (PAYLOAD / "assets" / "mobile.css").exists() and (PAYLOAD / "assets" / "mobile.js").exists()

    desktop_index = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert "mobile." not in desktop_index
    assert not (ROOT / "static" / "assets" / "mobile.css").exists()
    assert not (ROOT / "static" / "assets" / "mobile.js").exists()
    assert not (ROOT / "static" / "assets" / "extras.js").exists()

    # ذخیره‌ی عرض ستون‌ها فقط در bundle کپی اندروید است
    key = "finance-app:transactions-column-widths"
    android_bundle = next((PAYLOAD / "assets").glob("index-*.js")).read_text(encoding="utf-8")
    desktop_bundle = next((ROOT / "static" / "assets").glob("index-*.js")).read_text(encoding="utf-8")
    assert android_bundle.count(key) == 2 and key not in desktop_bundle


def test_mobile_css_turns_sidebar_into_drawer_and_unsticks_table_headers():
    css = (ROOT / "android" / "mobile" / "mobile.css").read_text(encoding="utf-8")
    assert "@media (max-width: 899px)" in css
    assert "#root aside" in css and "position: fixed" in css       # کشوی کناری
    assert "#root .sticky { position: static !important; }" in css  # سربرگ جدول روی ردیف‌ها نمی‌افتد
    js = (ROOT / "android" / "mobile" / "mobile.js").read_text(encoding="utf-8")
    assert "window.faBack" in js


def test_every_edit_target_has_a_definition_and_backend_route():
    """هر امضای جدول در extras.js باید به نوعی با تعریف ویرایش و مسیر PUT/DELETE در بک‌اند برسد."""
    js = (ROOT / "android" / "mobile" / "extras.js").read_text(encoding="utf-8")
    for kind in ("accounts", "transfers", "people", "debts", "loans", "sales", "categories", "tags", "budgets", "rules"):
        assert f"    {kind}: {{" in js, kind
    for route in ("/debts/' + id", "/loans/' + id", "/installment-sales/' + id", "/customers/' + c.id", "/tags/' + id", "/budgets/' + id", "/transfers/' + encodeURIComponent(id)"):
        assert route in js, route
