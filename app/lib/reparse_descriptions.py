"""بازپردازش description تراکنش‌های موجود — معادل src/lib/reparse-descriptions.ts."""
import sqlite3
from app.lib.description_parser import parse_transaction_description

_FIELDS = ("counterparty", "card_number", "iban", "bank_name", "reason")


def reparse_all_descriptions(conn: sqlite3.Connection, force: bool = False) -> dict:
    """
    force=False: ردیف‌هایی که از قبل حداقل یک فیلد استخراج‌شده دارند دست‌نخورده می‌مانند (رفتار قدیمی).
    force=True: «همه» تراکنش‌ها دوباره پردازش می‌شوند. هر فیلدی که parser مقدار پیدا کند جایگزین می‌شود؛
    فیلدی که parser چیزی برایش پیدا نکند (None) مقدار فعلی‌اش (مثلاً ورود دستی کاربر) حفظ می‌شود و پاک نمی‌شود.

    خروجی: total = کل تراکنش‌ها، processed = تعداد بررسی‌شده، updated = تعداد ردیف‌هایی که واقعاً تغییر کردند،
    skipped = تعداد ردیف‌های ردشده (فقط در حالت force=False).
    """
    rows = conn.execute(
        "SELECT id, description, counterparty, card_number, iban, bank_name, reason FROM transactions"
    ).fetchall()

    processed = updated = skipped = 0
    try:
        for row in rows:
            has_existing = row["counterparty"] or row["card_number"] or row["iban"] or row["bank_name"]
            if has_existing and not force:
                skipped += 1
                continue
            processed += 1
            parsed = parse_transaction_description(row["description"])

            if force:
                new_values = {f: (parsed[f] if parsed[f] is not None else row[f]) for f in _FIELDS}
            else:
                new_values = {f: parsed[f] for f in _FIELDS}

            if all(new_values[f] == row[f] for f in _FIELDS):
                continue
            conn.execute(
                "UPDATE transactions SET counterparty = ?, card_number = ?, iban = ?, bank_name = ?, reason = ? WHERE id = ?",
                (*(new_values[f] for f in _FIELDS), row["id"]),
            )
            updated += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {"updated": updated, "processed": processed, "skipped": skipped, "total": len(rows)}
