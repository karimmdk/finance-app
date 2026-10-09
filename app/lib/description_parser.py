"""
استخراج فیلدهای ساختاریافته از شرح تراکنش — معادل src/lib/description-parser.ts.
کاملاً deterministic (regex)، بدون AI.
"""
import re

KNOWN_BANKS = [
    "ملی", "ملت", "صادرات", "تجارت", "سپه", "کشاورزی", "مسکن", "رفاه", "پست بانک",
    "پارسیان", "پاسارگاد", "سامان", "سینا", "شهر", "دی", "گردشگری", "آینده", "اقتصاد نوین",
    "انصار", "قوامین", "کارآفرین", "خاورمیانه", "ایران زمین", "حکمت ایرانیان", "قرض‌الحسنه رسالت",
    "بلو", "آرین", "نور",
]
# نکته: تطبیق باید با مرز کلمه (\b) باشد، نه substring ساده — باگ واقعی پیدا‌شده: "دی" (بانک دی)
# به‌صورت ناخواسته داخل "احمدی" (نام‌خانوادگی) هم پیدا می‌شد چون فقط با `in` چک می‌شد.
_BANK_PATTERNS = [(bank, re.compile(rf"\b{re.escape(bank)}\b")) for bank in KNOWN_BANKS]

CARD_NUMBER_RE = re.compile(r"\b(\d{4}[\s-]?\*{2,4}[\s-]?\*{2,4}[\s-]?\d{4}|\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}|\d{16})\b")
IBAN_RE = re.compile(r"\b(IR\d{2}[\s-]?(?:\d{4}[\s-]?){5}\d{2}|IR\d{24})\b", re.IGNORECASE)
IBAN_LABELED_RE = re.compile(r"شبا[:\s]*([0-9]{20,26})")
# شماره سپرده/حساب — در فایل‌های واقعی بانکی (نمونه: "بلو") به‌جای شماره کارت واقعی می‌آید ولی
# همان نقش شناسه حساب طرف‌حساب را دارد؛ کاربر درخواست کرد در ستون شماره کارت نمایش داده شود.
ACCOUNT_NUMBER_LABELED_RE = re.compile(r"شماره\s*(?:سپرده|حساب)[:\s]*(\d{6,20})")
# نکته: بعد از کلیدواژه ممکن است ":" هم بیاید (مثل "بنام:") قبل از فاصله — [:\s]* هر دو حالت را می‌گیرد
COUNTERPARTY_RE = re.compile(r"(?:به\s*نام|بنام|آقای|خانم|جناب\s*آقای|سرکار\s*خانم)[:\s]+([آ-ی\s]{2,40}?)(?=[\s-]*(?:\d|شماره|کارت|شبا|بابت|بانک|$))")


def parse_transaction_description(description: str | None) -> dict:
    result = {"counterparty": None, "card_number": None, "iban": None, "bank_name": None, "reason": None}
    if not description:
        return result

    card_match = CARD_NUMBER_RE.search(description)
    if card_match:
        result["card_number"] = re.sub(r"[\s-]", "", card_match.group(1))
    else:
        account_match = ACCOUNT_NUMBER_LABELED_RE.search(description)
        if account_match:
            result["card_number"] = account_match.group(1)

    iban_match = IBAN_RE.search(description) or IBAN_LABELED_RE.search(description)
    if iban_match:
        raw = re.sub(r"[\s-]", "", iban_match.group(1))
        result["iban"] = raw.upper() if raw.upper().startswith("IR") else f"IR{raw}"

    for bank, pattern in _BANK_PATTERNS:
        if pattern.search(description):
            result["bank_name"] = bank
            break

    name_match = COUNTERPARTY_RE.search(description)
    if name_match:
        result["counterparty"] = name_match.group(1).strip()

    result["reason"] = description
    return result
