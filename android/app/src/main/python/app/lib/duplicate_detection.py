"""تشخیص تراکنش تکراری، سه‌حالته — معادل src/lib/duplicate-detection.ts. جزئیات: docs/duplicate-detection.md"""
from datetime import datetime
from dataclasses import dataclass


@dataclass
class NormalizedTransaction:
    account_id: int
    transaction_date: str  # ISO
    transaction_time: str | None
    amount: int
    type: str
    description: str | None
    document_number: str | None
    balance_after: int | None
    source_row_number: int | None
    raw_transaction_type: str | None = None


def _days_between(a: str, b: str) -> float:
    return abs((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()) / 86400


def _description_similar(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    na, nb = a.strip(), b.strip()
    if na == nb:
        return True
    shorter, longer = (na, nb) if len(na) < len(nb) else (nb, na)
    return longer.find(shorter[: min(20, len(shorter))]) != -1


def detect_duplicate(incoming: NormalizedTransaction, existing: list[dict]) -> dict:
    """
    existing: لیستی از dict با کلیدهای id, account_id, transaction_date, amount, type,
    document_number, description — باید از قبل به همان حساب محدود شده باشد.
    خروجی: {"status": "definite_duplicate"|"probable_duplicate"|"new", ...}
    """
    same_account = [e for e in existing if e["account_id"] == incoming.account_id]

    # 1) document_number دقیق — به‌همراه مبلغ و نوع.
    # نکته: در صورتحساب‌های بانکی یک شماره سند می‌تواند روی چند ردیف باشد (مثلاً یک سند «پرداخت تسهیلات» با
    # ردیف‌های جدا برای کارمزد، بازپرداخت و واریز اصلی). فقط‌ شماره سند، این ردیف‌های متفاوت را «تکراری قطعی»
    # می‌کرد و در ایمپورت هم‌پوشان، تراکنش واقعی بی‌صدا نادیده گرفته می‌شد.
    if incoming.document_number:
        for e in same_account:
            if (e["document_number"] == incoming.document_number
                    and e["amount"] == incoming.amount and e["type"] == incoming.type):
                return {"status": "definite_duplicate", "matched_transaction_id": e["id"], "reason": "document_number"}

    # 2) تاریخ + مبلغ + نوع دقیقاً یکسان
    # اگر هر دو طرف شماره سند دارند و متفاوت است، تراکنش‌ها قطعاً یکی نیستند (مثلاً دو واریز ۱۰۰ میلیونی
    # در یک روز به فاصله چند دقیقه) — نباید «تکراری قطعی» شمرده و حذف شوند.
    for e in same_account:
        if e["transaction_date"] == incoming.transaction_date and e["amount"] == incoming.amount and e["type"] == incoming.type:
            if incoming.document_number and e["document_number"] and e["document_number"] != incoming.document_number:
                continue
            return {"status": "definite_duplicate", "matched_transaction_id": e["id"], "reason": "date_amount_type_account"}

    # 3) تاریخ نزدیک (±۱ روز) + مبلغ یکسان
    for e in same_account:
        if _days_between(e["transaction_date"], incoming.transaction_date) <= 1 and e["amount"] == incoming.amount:
            boosted = _description_similar(e.get("description"), incoming.description)
            return {
                "status": "probable_duplicate",
                "matched_transaction_id": e["id"],
                "reason": "near_date_amount+similar_description" if boosted else "near_date_amount",
            }

    return {"status": "new"}
