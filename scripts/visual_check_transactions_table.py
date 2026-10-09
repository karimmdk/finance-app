"""
تست رگرسیون بصری برای جدول تراکنش‌ها — یک باگ واقعی و جدی اینجا پیدا شد که هیچ‌کدام از تست‌های
واحد/HTTP (vitest/supertest) نمی‌توانستند بگیرند: استفاده از <colgroup> همراه با
table-layout:fixed در ترکیب با dir="rtl" باعث می‌شد Chromium عرض ستون‌ها را به ترتیب سند
(چپ‌به‌راست) به ستون‌ها اختصاص دهد، در حالی که محتوای سلول‌ها به ترتیب بصری راست‌به‌چپ رندر
می‌شد — نتیجه: هر ستون داده‌ی ستون مجاورش را نشان می‌داد (مثلاً نام بانک زیر هدر «شبا»).
این باگ فقط با رندر واقعی در مرورگر و بررسی موقعیت واقعی DOM قابل کشف بود.

راه‌اندازی (یک‌بار):
    pip install playwright && python3 -m playwright install chromium

اجرا (سرور برنامه باید از قبل روی PORT مشخص‌شده در حال اجرا باشد):
    FINANCE_APP_URL=http://localhost:4000 python3 scripts/visual_check_transactions_table.py
"""
import os
import sys
from playwright.sync_api import sync_playwright

APP_URL = os.environ.get("FINANCE_APP_URL", "http://localhost:4000")


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1400, "height": 700})
        page.goto(APP_URL, wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(800)
        page.click("text=تراکنش‌ها")
        page.wait_for_timeout(1500)

        # نگاشت متن هدر -> ایندکس ستون، مستقیماً از DOM (نه از فرضیات کد)
        header_texts = page.eval_on_selector_all(
            "table thead th",
            "els => els.map(el => el.innerText.trim())"
        )
        header_index = {text.split("▲")[0].split("▼")[0].strip(): i for i, text in enumerate(header_texts) if text.strip()}

        first_row_cells = page.eval_on_selector_all(
            "table tbody tr:first-child td",
            "els => els.map(el => el.innerText.trim())"
        )

        errors = []

        bank_idx = header_index.get("بانک")
        iban_idx = header_index.get("شبا")  # ممکن است به‌طور پیش‌فرض پنهان باشد (فیچر نمایش/پنهان‌سازی ستون‌ها)
        card_idx = header_index.get("شماره کارت")

        if bank_idx is None or card_idx is None:
            errors.append(f"هدرهای مورد انتظار (بانک/شماره کارت) پیدا نشدند: {list(header_index.keys())}")
        else:
            bank_cell = first_row_cells[bank_idx] if bank_idx < len(first_row_cells) else None
            card_cell = first_row_cells[card_idx] if card_idx < len(first_row_cells) else None
            iban_cell = first_row_cells[iban_idx] if iban_idx is not None and iban_idx < len(first_row_cells) else None

            # ستون بانک نباید هرگز یک select/dropdown دسته‌بندی باشد و نباید متن IBAN-مانند (IR...) داشته باشد
            if bank_cell and bank_cell.startswith("IR"):
                errors.append(f"ستون «بانک» مقدار شبا نشان می‌دهد: {bank_cell!r}")
            # اگر ستون شبا نمایش داده شده، نباید نام یک بانک شناخته‌شده باشد
            if iban_cell in {"ملی", "ملت", "صادرات", "تجارت", "بلو"}:
                errors.append(f"ستون «شبا» نام بانک نشان می‌دهد: {iban_cell!r}")
            # ستون شماره کارت باید یا خالی باشد یا فقط رقم
            if card_cell and card_cell != "-" and not card_cell.replace("...", "").isdigit():
                errors.append(f"ستون «شماره کارت» مقدار غیرعددی دارد: {card_cell!r}")

        browser.close()

        if errors:
            print("FAIL — column alignment regression detected:")
            for e in errors:
                print(f"  - {e}")
            return 1

        print("OK — column headers align with their data (spot-checked بانک/شبا/شماره کارت)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
