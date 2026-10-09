"""موتور قوانین دسته‌بندی خودکار — معادل src/lib/rules-engine.ts.

نکات طراحی (رفع باگ «قانون جدید اعمال نمی‌شود»):
- قبلاً فقط «اولین» قانون منطبق اجرا می‌شد. چون قوانین پیش‌فرض (seed) روی «نوع تراکنش بانک» شناسه
  کوچک‌تری دارند، تقریباً هر تراکنشی زودتر با آن‌ها منطبق می‌شد و قوانین کاربر (مثلاً برچسب دیجیکالا
  بر اساس شماره پایانه) هرگز به نوبت نمی‌رسیدند. حالا «همه» قوانین فعال بررسی و نتایج ادغام می‌شوند:
    * برچسب‌ها (tagIds): اجتماع همه قوانین منطبق.
    * دسته‌بندی/شخص: قانون جدیدتر (شناسه بزرگ‌تر) روی قوانین قدیمی‌تر (مثل پیش‌فرض‌ها) غالب است.
- مقایسه متن نرمال‌سازی می‌شود (ارقام فارسی/عربی → انگلیسی، «ي/ك» عربی → «ی/ک»، حذف نیم‌فاصله و ...)
  تا «۸۲۰۰۰۲۲۱» و «82000221» یکسان دیده شوند.
- مقدار قانون می‌تواند چند گزینه (OR) باشد: جداکننده‌ها  |  ،  ؛  ;  ,  خط‌جدید  یا  «یا»/«or».
- مقدار کاملاً عددی (مثل شماره پایانه) به‌صورت «توکن عددی» تطبیق می‌شود: صفر ابتدایی اختیاری است
  (08975292 با 8975292 یکی است) و داخل یک عدد بلندتر پیدا نمی‌شود.
"""
import json
import re
import sqlite3

_DIGIT_MAP = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)
_CHAR_MAP = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه", "ة": "ه"})
_INVISIBLE_RE = re.compile("[\u200c\u200d\u200e\u200f\u202a-\u202e\u0640\u064b-\u065f]")
_WS_RE = re.compile(r"\s+")
_SPLIT_RE = re.compile(r"[|،؛;,\n\r]+|\s+(?:یا|or)\s+", re.IGNORECASE)
_PURE_NUMBER_RE = re.compile(r"^\d+$")


def normalize_text(value) -> str:
    """نرمال‌سازی متن برای مقایسه (ارقام، حروف عربی/فارسی، نیم‌فاصله، فاصله‌های اضافی)."""
    if value is None:
        return ""
    text = str(value).translate(_DIGIT_MAP).translate(_CHAR_MAP)
    text = _INVISIBLE_RE.sub("", text)
    return _WS_RE.sub(" ", text).strip().casefold()


def _split_values(raw_value) -> list[str]:
    """مقدار قانون را به چند گزینه (OR) می‌شکند؛ گزینه‌های خالی حذف می‌شوند."""
    # خط جدید باید قبل از نرمال‌سازی (که فاصله‌ها را یکی می‌کند) به جداکننده تبدیل شود
    text = normalize_text(re.sub(r"[\r\n]+", "|", str(raw_value)))
    return [part.strip() for part in _SPLIT_RE.split(text) if part.strip()]


def _to_number(value) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = normalize_text(value).replace(",", "").replace("٬", "").replace(" ", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _contains(haystack: str, needle: str) -> bool:
    if _PURE_NUMBER_RE.match(needle):
        stripped = needle.lstrip("0") or "0"
        return re.search(rf"(?<!\d)0*{re.escape(stripped)}(?!\d)", haystack) is not None
    return needle in haystack


def _condition_matches(condition: dict, txn: dict) -> bool:
    field = condition.get("field")
    op = condition.get("op")
    value = condition.get("value")
    if not field or value is None:
        return False
    field_value = txn.get("raw_transaction_type") if field == "rawTransactionType" else txn.get(field)

    # فیلد عددی (مبلغ): «contains» که فرم قوانین برای همه فیلدها می‌فرستد، اینجا یعنی «برابر با»
    if field == "amount":
        actual, expected = _to_number(field_value), _to_number(value)
        if actual is None or expected is None:
            return False
        if op in ("equals", "contains"):
            return actual == expected
        if op == "gt":
            return actual > expected
        if op == "lt":
            return actual < expected
        return False

    if op in ("gt", "lt"):
        actual, expected = _to_number(field_value), _to_number(value)
        if actual is None or expected is None:
            return False
        return actual > expected if op == "gt" else actual < expected

    if op not in ("contains", "equals"):
        return False
    if field_value is None or field_value == "":
        return False
    haystack = normalize_text(field_value)
    options = _split_values(value)
    if op == "contains":
        return any(_contains(haystack, opt) for opt in options)
    return any(haystack == opt for opt in options)


def load_active_rules(conn: sqlite3.Connection) -> list[dict]:
    """قوانین فعال به ترتیب شناسه (قدیمی → جدید)؛ condition/actions از قبل parse شده‌اند."""
    rules = []
    for row in conn.execute("SELECT * FROM rules WHERE active = 1 ORDER BY id ASC").fetchall():
        rule = dict(row)
        try:
            rule["condition"] = json.loads(row["condition"])
            rule["actions"] = json.loads(row["actions"])
        except (TypeError, ValueError):
            continue  # قانون خراب نباید کل اجرا را از کار بیندازد
        rules.append(rule)
    return rules


def evaluate_rules(rules: list[dict], txn: dict) -> dict:
    """
    همه قوانین منطبق را بررسی و نتیجه را ادغام می‌کند.
    خروجی: {"actions": {...ادغام‌شده از قوانین auto_apply}, "applied": [نام قوانین], "suggested": [نام قوانین]}
    قوانینِ فقط-پیشنهاد (auto_apply=0) هرگز در actions نمی‌آیند.
    """
    merged: dict = {}
    tag_ids: list[int] = []
    applied, suggested = [], []
    for rule in rules:
        if not _condition_matches(rule["condition"], txn):
            continue
        if not rule["auto_apply"]:
            suggested.append(rule["name"])
            continue
        applied.append(rule["name"])
        actions = rule["actions"]
        if actions.get("categoryId"):
            merged["categoryId"] = actions["categoryId"]
        if actions.get("personId"):
            merged["personId"] = actions["personId"]
        for tag_id in actions.get("tagIds") or []:
            if tag_id not in tag_ids:
                tag_ids.append(tag_id)
    if tag_ids:
        merged["tagIds"] = tag_ids
    return {"actions": merged, "applied": applied, "suggested": suggested}


def match_rules(conn: sqlite3.Connection, txn: dict) -> dict | None:
    """
    سازگاری با کد قبلی: اولین قانون منطبق. برای منطق جدید از load_active_rules + evaluate_rules
    استفاده کنید (که همه قوانین منطبق را ادغام می‌کند).
    """
    for rule in load_active_rules(conn):
        if _condition_matches(rule["condition"], txn):
            return {"rule": rule, "actions": rule["actions"], "auto_apply": bool(rule["auto_apply"])}
    return None


def apply_rule_actions(conn: sqlite3.Connection, transaction_id: int, actions: dict,
                       overwrite: bool = True, commit: bool = True) -> bool:
    """
    actions را روی تراکنش اعمال می‌کند و اگر چیزی واقعاً تغییر کرد True برمی‌گرداند.
    overwrite=False: دسته/شخصِ موجود را عوض نمی‌کند (فقط جای خالی را پر می‌کند). برچسب‌ها همیشه اضافه می‌شوند.
    commit=False: برای استفاده داخل یک تراکنش بزرگ‌تر (مثل import) — تا rollback کامل کار کند.
    """
    changed = False
    row = conn.execute("SELECT category_id, person_id FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if row is None:
        return False

    new_category = actions.get("categoryId")
    if new_category and new_category != row["category_id"] and (overwrite or row["category_id"] is None):
        conn.execute("UPDATE transactions SET category_id = ? WHERE id = ?", (new_category, transaction_id))
        changed = True

    new_person = actions.get("personId")
    if new_person and new_person != row["person_id"] and (overwrite or row["person_id"] is None):
        conn.execute("UPDATE transactions SET person_id = ? WHERE id = ?", (new_person, transaction_id))
        changed = True

    for tag_id in actions.get("tagIds") or []:
        cur = conn.execute(
            "INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (transaction_id, tag_id)
        )
        if cur.rowcount:
            changed = True

    if commit:
        conn.commit()
    return changed
