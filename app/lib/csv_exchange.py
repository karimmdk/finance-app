"""
خروجی/ورودی CSV دوطرفه (round-trip) برای تراکنش‌ها، دسته‌بندی‌ها و برچسب‌ها.

چرا فرمت قبلی قابل درون‌ریزی نبود؟
  CSV قبلی فقط شناسه‌های عددی (account_id, category_id, person_id) داشت، هیچ ستون برچسبی نداشت و
  نام حساب/ساعت/طرف‌حساب و ... را هم نمی‌داد. شناسه‌ها فقط در همان دیتابیس معنی دارند؛ پس فایل نه اطلاعات
  دسته و برچسب را به کاربر می‌داد و نه در دیتابیس دیگری قابل استفاده بود.

فرمت جدید (همه چیز با «نام» است، نه شناسه):
  * فایل تراکنش‌ها: حساب، تاریخ (میلادی + شمسی برای خواندن)، ساعت، نوع، مبلغ، شرح، شماره سند، فیلدهای
    استخراج‌شده، دسته‌بندی (مسیر کامل «والد > فرزند»)، شخص، برچسب‌ها (جداشده با «|»)، یادداشت و ...
  * فایل دسته‌بندی‌ها و برچسب‌ها: فهرست «همه» دسته‌ها و برچسب‌ها (حتی بدون تراکنش) با رنگ و تعداد استفاده.

درون‌ریزی: هر دو فایل توسط همین ماژول خوانده می‌شوند؛ آنچه وجود ندارد (دسته، برچسب، شخص، حساب) ساخته می‌شود.
"""
import csv
import io
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from app.lib.description_parser import parse_transaction_description
from app.lib.duplicate_detection import NormalizedTransaction, detect_duplicate
from app.lib.jalali import iso_to_jalali, jalali_to_iso
from app.lib.rules_engine import apply_rule_actions, evaluate_rules, load_active_rules, normalize_text

TRANSACTION_COLUMNS = [
    "id", "account", "transaction_date", "jalali_date", "transaction_time", "type", "amount", "balance_after",
    "description", "document_number", "counterparty", "card_number", "iban", "bank_name", "reason",
    "raw_transaction_type", "category", "person", "tags", "notes", "excluded_from_analysis", "transfer_id",
]
TAXONOMY_COLUMNS = ["kind", "name", "color", "icon", "transaction_count"]

VALID_TYPES = {"income", "expense", "transfer", "adjustment"}
_TYPE_ALIASES = {
    "درآمد": "income", "دریافت": "income", "واریز": "income", "ورودی": "income", "credit": "income",
    "هزینه": "expense", "پرداخت": "expense", "برداشت": "expense", "خروجی": "expense", "debit": "expense",
    "انتقال": "transfer", "جابجایی": "transfer",
    "اصلاح": "adjustment", "اصلاحی": "adjustment", "اصلاح سند": "adjustment", "تعدیل": "adjustment",
}

# نام‌های قابل قبول هر ستون (کلیدها پس از normalize مقایسه می‌شوند) — فایل دست‌ساز با سرستون فارسی هم پذیرفته می‌شود
_ALIASES = {
    "id": ["id", "شناسه"],
    "account": ["account", "accountname", "حساب", "نامحساب"],
    "account_id": ["accountid"],
    "transaction_date": ["transactiondate", "date", "تاریخ", "تاریخمیلادی"],
    "jalali_date": ["jalalidate", "تاریخشمسی", "تاریخجلالی"],
    "transaction_time": ["transactiontime", "time", "ساعت", "زمان"],
    "type": ["type", "نوع"],
    "amount": ["amount", "مبلغ"],
    "balance_after": ["balanceafter", "balance", "مانده"],
    "description": ["description", "شرح", "شرحسند", "توضیحات"],
    "document_number": ["documentnumber", "doc", "شمارهسند"],
    "counterparty": ["counterparty", "طرفحساب"],
    "card_number": ["cardnumber", "شمارهکارت"],
    "iban": ["iban", "شبا", "شمارهشبا"],
    "bank_name": ["bankname", "بانک", "نامبانک"],
    "reason": ["reason", "بابت", "دلیل"],
    "raw_transaction_type": ["rawtransactiontype", "نوعتراکنش", "نوعتراکنشبانک"],
    "category": ["category", "دسته", "دستهبندی"],
    "category_id": ["categoryid"],
    "person": ["person", "شخص"],
    "person_id": ["personid"],
    "tags": ["tags", "tag", "برچسب", "برچسبها"],
    "notes": ["notes", "note", "یادداشت", "یادداشتها"],
    "excluded_from_analysis": ["excludedfromanalysis", "exclude", "خارجازآنالیز", "استثنا"],
    "transfer_id": ["transferid"],
    "kind": ["kind", "نوعرکورد"],
    "name": ["name", "نام"],
    "color": ["color", "رنگ"],
    "icon": ["icon", "آیکون"],
    "transaction_count": ["transactioncount", "تعدادتراکنش"],
}

_TAG_SEPS = "|،;؛"
_CAT_SEPS = ">"
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_SCI_NOTATION_RE = re.compile(r"^\d(?:\.\d+)?[eE]\+\d+$")


class CsvFormatError(ValueError):
    """فایل CSV قابل فهم نیست (پیام فارسی برای نمایش به کاربر)."""


# ───────────────────────────── ابزارهای پایه ─────────────────────────────
def _hkey(text) -> str:
    return re.sub(r"[\s_\-]+", "", normalize_text(text))


_ALIAS_LOOKUP = {_hkey(alias): canon for canon, aliases in _ALIASES.items() for alias in aliases}


def _escape(value: str, special: str) -> str:
    out = []
    for ch in value:
        if ch == "\\" or ch in special:
            out.append("\\")
        out.append(ch)
    return "".join(out)


def _split_escaped(text: str, seps: str) -> list[str]:
    parts, cur, i = [], [], 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            cur.append(text[i + 1])
            i += 2
            continue
        if ch in seps:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _safe_cell(value) -> str:
    """جلوگیری از «تزریق فرمول» در Excel: متنی که با = + - @ شروع شود با ' ایمن می‌شود (در ورودی برمی‌گردد)."""
    if value is None:
        return ""
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def _unsafe_cell(value: str) -> str:
    if len(value) > 1 and value[0] == "'" and value[1] in "=+-@\t\r":
        return value[1:]
    return value


def _decode(content: bytes) -> tuple[str, bool]:
    """(متن, آیا با cp1256 خوانده شد). Excel فارسی‌ویندوز گاهی «CSV» را با cp1256 ذخیره می‌کند."""
    if content.startswith(b"\xef\xbb\xbf"):
        return content[3:].decode("utf-8"), False
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16"), False
    try:
        return content.decode("utf-8"), False
    except UnicodeDecodeError:
        pass
    try:
        return content.decode("cp1256"), True
    except UnicodeDecodeError:
        raise CsvFormatError("رمزگذاری فایل قابل تشخیص نیست؛ فایل را با UTF-8 ذخیره کنید (در Excel: CSV UTF-8)")


def _read_table(content: bytes) -> tuple[list[str], list[tuple[int, dict]]]:
    """(ستون‌های canonical, [(شماره ردیف, {ستون: مقدار})]) — ردیف‌های کاملاً خالی حذف می‌شوند."""
    text, legacy_enc = _decode(content)
    if legacy_enc:
        text = text.translate(str.maketrans({"ي": "ی", "ك": "ک"}))
    text = text.lstrip("\ufeff")
    first_line = text.split("\n", 1)[0]
    delimiter = max(",;\t", key=first_line.count)
    if first_line.count(delimiter) == 0:
        raise CsvFormatError("فایل CSV خالی است یا سرستون ندارد")

    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        header_raw = next(reader)
    except StopIteration:
        raise CsvFormatError("فایل CSV خالی است")

    columns: list[str | None] = []
    seen: set[str] = set()
    for h in header_raw:
        canon = _ALIAS_LOOKUP.get(_hkey(h))
        if canon and canon not in seen:
            seen.add(canon)
            columns.append(canon)
        else:
            columns.append(None)

    rows = []
    for i, raw in enumerate(reader, start=2):
        if not any(cell.strip() for cell in raw):
            continue
        record = {}
        for col, cell in zip(columns, raw):
            if col:
                record[col] = _unsafe_cell(cell.strip())
        rows.append((i, record))
    return [c for c in columns if c], rows


def sniff_csv_kind(content: bytes) -> str:
    """'transactions' | 'taxonomy' — یا CsvFormatError اگر فرمت ناشناخته باشد."""
    columns, _ = _read_table(content)
    cols = set(columns)
    if {"kind", "name"} <= cols and "amount" not in cols:
        return "taxonomy"
    if "amount" in cols and ({"transaction_date", "jalali_date"} & cols):
        return "transactions"
    raise CsvFormatError(
        "ساختار CSV شناخته نشد. فایل تراکنش‌ها باید حداقل ستون‌های «amount» و «transaction_date» را داشته باشد "
        "و فایل دسته‌بندی/برچسب ستون‌های «kind» و «name» را."
    )


def _parse_amount(text: str) -> int | None:
    cleaned = normalize_text(text).replace(",", "").replace("٬", "").replace(" ", "")
    if not cleaned:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    try:
        value = int(Decimal(cleaned).to_integral_value())
    except (InvalidOperation, ValueError):
        return None
    return -value if negative else value


def _parse_date_time(text: str) -> tuple[str | None, str | None]:
    s = normalize_text(text)
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ t](\d{1,2}:\d{2}(?::\d{2})?))?", s)
    if not m:
        return None, None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        iso = jalali_to_iso(f"{y}/{mo}/{d}") if y < 1700 else date(y, mo, d).isoformat()
    except ValueError:
        return None, None
    return iso, m.group(4)


def _norm_time(text: str) -> str | None:
    s = normalize_text(text)
    m = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", s)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}:{m.group(3) or '00'}"


def _parse_type(text: str) -> str | None:
    s = normalize_text(text)
    if s in VALID_TYPES:
        return s
    return _TYPE_ALIASES.get(s)


def _truthy(text: str) -> int:
    return 1 if normalize_text(text) in {"1", "true", "yes", "y", "بله", "آره", "✓"} else 0


# ───────────────────────────── خروجی ─────────────────────────────
def _category_paths(conn: sqlite3.Connection) -> dict[int, str]:
    cats = {r["id"]: (r["name"], r["parent_id"]) for r in conn.execute("SELECT id, name, parent_id FROM categories")}
    paths: dict[int, str] = {}
    for cid in cats:
        parts, cur, guard = [], cid, 0
        while cur is not None and cur in cats and guard < 20:
            name, parent = cats[cur]
            parts.append(_escape(name, _CAT_SEPS))
            cur, guard = parent, guard + 1
        paths[cid] = " > ".join(reversed(parts))
    return paths


def _write_csv(columns: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM برای نمایش صحیح فارسی در Excel
    writer = csv.writer(buf)
    writer.writerow(columns)
    writer.writerows(rows)
    return buf.getvalue()


def export_transactions_csv(conn: sqlite3.Connection) -> str:
    paths = _category_paths(conn)
    tags_by_txn: dict[int, list[str]] = {}
    for r in conn.execute(
        "SELECT tt.transaction_id AS tid, tg.name FROM transaction_tags tt JOIN tags tg ON tg.id = tt.tag_id ORDER BY tg.name"
    ):
        tags_by_txn.setdefault(r["tid"], []).append(_escape(r["name"], _TAG_SEPS))

    rows = []
    for t in conn.execute(
        """SELECT t.*, a.name AS account_name, p.name AS person_name
           FROM transactions t
           JOIN accounts a ON a.id = t.account_id
           LEFT JOIN people p ON p.id = t.person_id
           ORDER BY t.transaction_date, t.transaction_time, t.id"""
    ):
        try:
            jalali = iso_to_jalali(t["transaction_date"])
        except Exception:
            jalali = ""
        text = _safe_cell
        rows.append([
            t["id"], text(t["account_name"]), t["transaction_date"], jalali, t["transaction_time"] or "",
            t["type"], t["amount"], "" if t["balance_after"] is None else t["balance_after"],
            text(t["description"]), text(t["document_number"]), text(t["counterparty"]), text(t["card_number"]),
            text(t["iban"]), text(t["bank_name"]), text(t["reason"]), text(t["raw_transaction_type"]),
            text(paths.get(t["category_id"], "")) if t["category_id"] else "",
            text(t["person_name"]), text(" | ".join(tags_by_txn.get(t["id"], []))),
            text(t["notes"]), t["excluded_from_analysis"] or 0, t["transfer_id"] or "",
        ])
    return _write_csv(TRANSACTION_COLUMNS, rows)


def export_taxonomy_csv(conn: sqlite3.Connection) -> str:
    """همه دسته‌بندی‌ها و برچسب‌ها — حتی آن‌هایی که هیچ تراکنشی ندارند."""
    paths = _category_paths(conn)
    cat_counts = {r["category_id"]: r["c"] for r in conn.execute(
        "SELECT category_id, COUNT(*) AS c FROM transactions WHERE category_id IS NOT NULL GROUP BY category_id")}
    tag_counts = {r["tag_id"]: r["c"] for r in conn.execute(
        "SELECT tag_id, COUNT(*) AS c FROM transaction_tags GROUP BY tag_id")}

    rows = []
    for c in sorted(conn.execute("SELECT * FROM categories").fetchall(), key=lambda r: paths[r["id"]]):
        rows.append(["category", _safe_cell(paths[c["id"]]), c["color"] or "", c["icon"] or "", cat_counts.get(c["id"], 0)])
    for tg in conn.execute("SELECT * FROM tags ORDER BY name"):
        rows.append(["tag", _safe_cell(tg["name"]), tg["color"] or "", "", tag_counts.get(tg["id"], 0)])
    return _write_csv(TAXONOMY_COLUMNS, rows)


# ───────────────────────────── نام‌ها ← شناسه ─────────────────────────────
class _Resolver:
    """
    نام حساب/دسته/شخص/برچسب را به شناسه تبدیل می‌کند. dry_run=True: چیزی نمی‌سازد و فقط «ناموجودها» را ثبت می‌کند
    (برای پیش‌نمایش). dry_run=False: موارد ناموجود ساخته می‌شوند (داخل تراکنش اتمیک import).
    """

    def __init__(self, conn: sqlite3.Connection, dry_run: bool):
        self.conn, self.dry_run = conn, dry_run
        self.missing = {"accounts": [], "categories": [], "tags": [], "people": []}
        self.created = {"accounts": 0, "categories": 0, "tags": 0, "people": 0}
        self._accounts = {normalize_text(r["name"]): r["id"] for r in conn.execute("SELECT id, name FROM accounts")}
        self._people = {normalize_text(r["name"]): r["id"] for r in conn.execute("SELECT id, name FROM people")}
        self._tags = {normalize_text(r["name"]): r["id"] for r in conn.execute("SELECT id, name FROM tags")}
        self._cats = {(r["parent_id"], normalize_text(r["name"])): r["id"]
                      for r in conn.execute("SELECT id, name, parent_id FROM categories")}
        self._virtual_seen: set = set()

    def _miss(self, kind: str, name: str):
        if name not in self.missing[kind]:
            self.missing[kind].append(name)

    def account(self, name: str) -> int | None:
        key = normalize_text(name)
        if key in self._accounts:
            return self._accounts[key]
        self._miss("accounts", name)
        if self.dry_run:
            return None
        new_id = self.conn.execute(
            "INSERT INTO accounts (name, type, initial_balance) VALUES (?, 'bank', 0)", (name,)).lastrowid
        self._accounts[key] = new_id
        self.created["accounts"] += 1
        return new_id

    def person(self, name: str) -> int | None:
        key = normalize_text(name)
        if key in self._people:
            return self._people[key]
        self._miss("people", name)
        if self.dry_run:
            return None
        new_id = self.conn.execute("INSERT INTO people (name) VALUES (?)", (name,)).lastrowid
        self._people[key] = new_id
        self.created["people"] += 1
        return new_id

    def tag(self, name: str) -> int | None:
        key = normalize_text(name)
        if key in self._tags:
            return self._tags[key]
        self._miss("tags", name)
        if self.dry_run:
            return None
        new_id = self.conn.execute("INSERT INTO tags (name) VALUES (?)", (name,)).lastrowid
        self._tags[key] = new_id
        self.created["tags"] += 1
        return new_id

    def category_path(self, path: str) -> int | None:
        parts = _split_escaped(path, _CAT_SEPS)
        if not parts:
            return None
        if len(parts) == 1:
            # نام تنها (فایل دست‌ساز): اول سطح بالا، بعد اگر فقط یک دسته با این نام در هر سطحی هست همان
            key = normalize_text(parts[0])
            if (None, key) in self._cats:
                return self._cats[(None, key)]
            same_name = [cid for (_, k), cid in self._cats.items() if k == key]
            if len(same_name) == 1:
                return same_name[0]
        parent = None
        for idx, name in enumerate(parts):
            key = (parent, normalize_text(name))
            if key in self._cats:
                parent = self._cats[key]
                continue
            self._miss("categories", " > ".join(parts[: idx + 1]))
            if self.dry_run:
                return None
            parent = self.conn.execute("INSERT INTO categories (name, parent_id) VALUES (?, ?)", (name, parent)).lastrowid
            self._cats[key] = parent
            self.created["categories"] += 1
        return parent


# ───────────────────────────── پارس فایل تراکنش‌ها ─────────────────────────────
@dataclass
class CsvTransaction(NormalizedTransaction):
    row_number: int = 0
    account_name: str | None = None
    category_path: str | None = None
    person_name: str | None = None
    tags: list = field(default_factory=list)
    notes: str | None = None
    counterparty: str | None = None
    card_number: str | None = None
    iban: str | None = None
    bank_name: str | None = None
    reason: str | None = None
    excluded: int = 0
    transfer_id: str | None = None
    legacy_category_id: int | None = None
    legacy_person_id: int | None = None


def parse_transactions_csv(content: bytes, conn: sqlite3.Connection, default_account_id: int | None) -> dict:
    columns, rows = _read_table(content)
    cols = set(columns)
    accounts = {normalize_text(r["name"]): r["id"] for r in conn.execute("SELECT id, name FROM accounts")}
    account_ids = {r["id"] for r in conn.execute("SELECT id FROM accounts")}

    notes: list[str] = []
    if "account" not in cols and "account_id" in cols:
        notes.append("فایل قدیمی است (ستون «account_id»): حساب‌ها بر اساس شناسه عددی تطبیق داده شدند.")
    if "category_id" in cols and "category" not in cols:
        notes.append("ستون «category_id» قدیمی است: فقط شناسه‌هایی که در این دیتابیس وجود دارند تطبیق داده شدند. "
                     "برای انتقال بین دیتابیس‌ها، فایل را دوباره از نسخه جدید خروجی بگیرید (نام دسته‌بندی را می‌دهد).")

    transactions: list[CsvTransaction] = []
    issues: list[dict] = []

    def issue(row_no: int, msg: str):
        issues.append({"row_number": row_no, "rowNumber": row_no, "message": msg})

    def clean_id(row_no: int, label: str, value: str) -> str | None:
        if not value:
            return None
        if _SCI_NOTATION_RE.match(value):
            issue(row_no, f"«{label}» توسط Excel به نمایش علمی خراب شده ({value}) و نادیده گرفته شد")
            return None
        return value

    for row_no, r in rows:
        # ── تاریخ
        iso, time_from_date = (None, None)
        if r.get("transaction_date"):
            iso, time_from_date = _parse_date_time(r["transaction_date"])
        if iso is None and r.get("jalali_date"):
            iso, time_from_date = _parse_date_time(r["jalali_date"])
        if iso is None:
            issue(row_no, "تاریخ نامعتبر یا خالی است — ردیف نادیده گرفته شد")
            continue
        time_value = _norm_time(r.get("transaction_time", "")) or (_norm_time(time_from_date) if time_from_date else None)

        # ── مبلغ و نوع
        amount = _parse_amount(r.get("amount", ""))
        if amount is None:
            issue(row_no, "مبلغ نامعتبر یا خالی است — ردیف نادیده گرفته شد")
            continue
        type_raw = r.get("type", "")
        txn_type = _parse_type(type_raw) if type_raw else ("expense" if amount < 0 else "income")
        if txn_type is None:
            issue(row_no, f"نوع تراکنش نامعتبر است: «{type_raw}» — ردیف نادیده گرفته شد")
            continue
        amount = abs(amount)
        if amount == 0:
            issue(row_no, "مبلغ تراکنش صفر است — ردیف نادیده گرفته شد")
            continue

        # ── حساب
        account_name = r.get("account") or None
        account_id = None
        if account_name:
            account_id = accounts.get(normalize_text(account_name))
        elif r.get("account_id", "").isdigit() and int(r["account_id"]) in account_ids:
            account_id = int(r["account_id"])
        elif default_account_id is not None:
            account_id = default_account_id
        else:
            issue(row_no, "حساب مشخص نیست (نه ستون حساب دارد نه حساب پیش‌فرض انتخاب شده) — ردیف نادیده گرفته شد")
            continue

        balance = _parse_amount(r.get("balance_after", "")) if r.get("balance_after") else None
        legacy_cat = int(r["category_id"]) if r.get("category_id", "").isdigit() else None
        legacy_person = int(r["person_id"]) if r.get("person_id", "").isdigit() else None

        transactions.append(CsvTransaction(
            account_id=account_id, transaction_date=iso, transaction_time=time_value, amount=amount, type=txn_type,
            description=r.get("description") or None,
            document_number=clean_id(row_no, "شماره سند", r.get("document_number", "")),
            balance_after=balance, source_row_number=row_no,
            raw_transaction_type=r.get("raw_transaction_type") or None,
            row_number=row_no, account_name=account_name,
            category_path=r.get("category") or None, person_name=r.get("person") or None,
            tags=_split_escaped(r.get("tags", ""), _TAG_SEPS),
            notes=r.get("notes") or None, counterparty=r.get("counterparty") or None,
            card_number=clean_id(row_no, "شماره کارت", r.get("card_number", "")),
            iban=clean_id(row_no, "شبا", r.get("iban", "")),
            bank_name=r.get("bank_name") or None, reason=r.get("reason") or None,
            excluded=_truthy(r.get("excluded_from_analysis", "")),
            transfer_id=clean_id(row_no, "شناسه انتقال", r.get("transfer_id", "")),
            legacy_category_id=legacy_cat, legacy_person_id=legacy_person,
        ))
    return {"transactions": transactions, "issues": issues, "notes": notes, "columns": columns}


# ───────────────────────────── پیش‌نمایش ─────────────────────────────
def _existing_by_account(conn: sqlite3.Connection) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for r in conn.execute(
        "SELECT id, account_id, transaction_date, amount, type, document_number, description, category_id, person_id "
        "FROM transactions"
    ):
        grouped.setdefault(r["account_id"], []).append(dict(r))
    return grouped


def _tag_names_of(conn: sqlite3.Connection, txn_id: int) -> set[str]:
    return {normalize_text(r["name"]) for r in conn.execute(
        "SELECT tg.name FROM tags tg JOIN transaction_tags tt ON tt.tag_id = tg.id WHERE tt.transaction_id = ?", (txn_id,))}


def _resolve_legacy(conn, t: CsvTransaction) -> tuple[int | None, int | None]:
    cat = t.legacy_category_id if t.legacy_category_id and conn.execute(
        "SELECT 1 FROM categories WHERE id = ?", (t.legacy_category_id,)).fetchone() else None
    person = t.legacy_person_id if t.legacy_person_id and conn.execute(
        "SELECT 1 FROM people WHERE id = ?", (t.legacy_person_id,)).fetchone() else None
    return cat, person


def _would_update(conn, resolver: _Resolver, t: CsvTransaction, matched_id: int, existing_row: dict | None) -> bool:
    if existing_row is None:
        return False
    if t.category_path:
        cid = resolver.category_path(t.category_path)
        if cid is None or cid != existing_row["category_id"]:
            return True
    elif t.legacy_category_id:
        cid, _ = _resolve_legacy(conn, t)
        if cid and cid != existing_row["category_id"]:
            return True
    if t.person_name:
        pid = resolver.person(t.person_name)
        if pid is None or pid != existing_row["person_id"]:
            return True
    if t.tags:
        current = _tag_names_of(conn, matched_id)
        if any(normalize_text(name) not in current for name in t.tags):
            return True
    return False


def preview_transactions_csv(conn: sqlite3.Connection, parsed: dict, update_existing: bool = True) -> dict:
    existing = _existing_by_account(conn)
    by_id = {e["id"]: e for rows in existing.values() for e in rows}
    resolver = _Resolver(conn, dry_run=True)

    preview = []
    for idx, t in enumerate(parsed["transactions"]):
        if t.account_id is None:
            resolver.account(t.account_name)  # فقط ثبت به‌عنوان «حساب جدید»
            dup = {"status": "new"}
        else:
            dup = detect_duplicate(t, existing.get(t.account_id, []))
        will_update = False
        if dup["status"] == "definite_duplicate" and update_existing:
            will_update = _would_update(conn, resolver, t, dup["matched_transaction_id"], by_id.get(dup["matched_transaction_id"]))
        elif dup["status"] != "definite_duplicate":
            if t.category_path:
                resolver.category_path(t.category_path)
            if t.person_name:
                resolver.person(t.person_name)
            for name in t.tags:
                resolver.tag(name)
        dup_out = {"status": dup["status"]}
        if "matched_transaction_id" in dup:
            dup_out["matchedTransactionId"] = dup["matched_transaction_id"]
        if "reason" in dup:
            dup_out["reason"] = dup["reason"]
        preview.append({
            "index": idx,
            "transaction": {
                "accountId": t.account_id, "accountName": t.account_name, "transactionDate": t.transaction_date,
                "transactionTime": t.transaction_time, "amount": t.amount, "type": t.type,
                "description": t.description, "documentNumber": t.document_number,
                "balanceAfter": t.balance_after, "sourceRowNumber": t.source_row_number,
                "rawTransactionType": t.raw_transaction_type,
                "categoryName": t.category_path, "personName": t.person_name, "tags": t.tags,
            },
            "duplicateResult": dup_out,
            "taxonomyChange": will_update,
        })

    statuses = [p["duplicateResult"]["status"] for p in preview]
    m = resolver.missing
    info = list(parsed["notes"])
    if m["accounts"]:
        info.append("حساب‌های زیر وجود ندارند و هنگام ثبت ساخته می‌شوند (موجودی اولیه ۰): " + "، ".join(m["accounts"]))
    if m["categories"]:
        info.append(f"{len(m['categories'])} دسته‌بندی جدید ساخته می‌شود: " + "، ".join(m["categories"][:15])
                    + (" ..." if len(m["categories"]) > 15 else ""))
    if m["tags"]:
        info.append(f"{len(m['tags'])} برچسب جدید ساخته می‌شود: " + "، ".join(m["tags"][:15])
                    + (" ..." if len(m["tags"]) > 15 else ""))
    if m["people"]:
        info.append(f"{len(m['people'])} شخص جدید ساخته می‌شود: " + "، ".join(m["people"][:15]))
    updates = sum(1 for p in preview if p["taxonomyChange"])
    if updates:
        info.append(f"دسته‌بندی/برچسب/شخص {updates} تراکنش موجود (تکراری) از روی فایل به‌روزرسانی می‌شود.")

    return {
        "kind": "transactions_csv",
        "headerMeta": {},
        "issues": parsed["issues"],
        "preview": preview,
        "summary": {
            "total": len(preview),
            "new": statuses.count("new"),
            "definiteDuplicate": statuses.count("definite_duplicate"),
            "probableDuplicate": statuses.count("probable_duplicate"),
            "adjustment": sum(1 for p in preview if p["transaction"]["type"] == "adjustment"),
            "taxonomyUpdates": updates,
            "notes": info,
        },
    }


# ───────────────────────────── ثبت نهایی ─────────────────────────────
def commit_transactions_csv(conn: sqlite3.Connection, parsed: dict, file_name: str,
                            decisions: dict[int, str] | None = None, apply_rules: bool = False,
                            update_existing: bool = True) -> dict:
    """کل عملیات در یک تراکنش اتمیک: خطا = rollback کامل (شامل حساب/دسته/برچسب‌هایی که ساخته شده بودند)."""
    existing = _existing_by_account(conn)
    by_id = {e["id"]: e for rows in existing.values() for e in rows}
    rules = load_active_rules(conn) if apply_rules else []
    resolver = _Resolver(conn, dry_run=False)

    new_count = definite = probable = updated = rules_applied = 0
    per_account_new: dict[int, int] = {}
    per_account_dup: dict[int, int] = {}
    batches: dict[int, int] = {}

    def batch_for(account_id: int) -> int:
        if account_id not in batches:
            batches[account_id] = conn.execute(
                "INSERT INTO import_batches (account_id, file_name, adapter, imported_count, duplicate_count, status) "
                "VALUES (?, ?, 'app-csv', 0, 0, 'completed')", (account_id, file_name)).lastrowid
        return batches[account_id]

    try:
        for idx, t in enumerate(parsed["transactions"]):
            if t.account_id is None:
                account_id = resolver.account(t.account_name)
                dup = {"status": "new"}
            else:
                account_id = t.account_id
                dup = detect_duplicate(t, existing.get(account_id, []))

            if dup["status"] == "definite_duplicate":
                definite += 1
                per_account_dup[account_id] = per_account_dup.get(account_id, 0) + 1
            elif dup["status"] == "probable_duplicate":
                probable += 1
                per_account_dup[account_id] = per_account_dup.get(account_id, 0) + 1

            # به‌روزرسانی دسته/شخص/برچسب تراکنش موجود (مستقل از تیک «ثبت»، چون تراکنش جدیدی ساخته نمی‌شود)
            if dup["status"] == "definite_duplicate" and update_existing:
                if _update_existing(conn, resolver, t, dup["matched_transaction_id"], by_id.get(dup["matched_transaction_id"])):
                    updated += 1

            decision = (decisions or {}).get(idx, "ignore" if dup["status"] == "definite_duplicate" else "import")
            if decision != "import":
                continue

            cat_id = resolver.category_path(t.category_path) if t.category_path else None
            person_id = resolver.person(t.person_name) if t.person_name else None
            if t.legacy_category_id and not t.category_path:
                cat_id, _ = _resolve_legacy(conn, t)
            if t.legacy_person_id and not t.person_name:
                _, person_id = _resolve_legacy(conn, t)
            tag_ids = [resolver.tag(n) for n in t.tags]

            auto = parse_transaction_description(t.description)
            cur = conn.execute(
                """INSERT INTO transactions
                   (account_id, transaction_date, transaction_time, amount, type, balance_after, description,
                    document_number, counterparty, category_id, person_id, notes, source, import_batch_id,
                    transfer_id, source_row_number, card_number, iban, bank_name, reason, raw_transaction_type,
                    excluded_from_analysis)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'import', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (account_id, t.transaction_date, t.transaction_time, t.amount, t.type, t.balance_after, t.description,
                 t.document_number, t.counterparty or auto["counterparty"], cat_id, person_id, t.notes,
                 batch_for(account_id), t.transfer_id, t.source_row_number,
                 t.card_number or auto["card_number"], t.iban or auto["iban"], t.bank_name or auto["bank_name"],
                 t.reason or auto["reason"], t.raw_transaction_type, t.excluded),
            )
            txn_id = cur.lastrowid
            for tag_id in tag_ids:
                conn.execute("INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (txn_id, tag_id))
            new_count += 1
            per_account_new[account_id] = per_account_new.get(account_id, 0) + 1

            # قوانین فقط برای ردیف‌هایی که در فایل نه دسته دارند نه برچسب (فایل «منبع حقیقت» است)
            if apply_rules and rules and cat_id is None and not tag_ids:
                result = evaluate_rules(rules, {
                    "description": t.description, "counterparty": t.counterparty or auto["counterparty"],
                    "amount": t.amount, "type": t.type, "raw_transaction_type": t.raw_transaction_type})
                if result["actions"] and apply_rule_actions(conn, txn_id, result["actions"], overwrite=False, commit=False):
                    rules_applied += 1

        for account_id, batch_id in batches.items():
            conn.execute("UPDATE import_batches SET imported_count = ?, duplicate_count = ? WHERE id = ?",
                         (per_account_new.get(account_id, 0), per_account_dup.get(account_id, 0), batch_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "batch_id": next(iter(batches.values()), None), "batch_ids": list(batches.values()),
        "total": len(parsed["transactions"]),
        "new_count": new_count, "newCount": new_count,
        "definite_duplicate_count": definite, "definiteDuplicateCount": definite,
        "probable_duplicate_count": probable, "probableDuplicateCount": probable,
        "updated_count": updated, "updatedCount": updated,
        "rules_applied_count": rules_applied, "rulesApplied": rules_applied,
        "createdAccounts": resolver.created["accounts"], "createdCategories": resolver.created["categories"],
        "createdTags": resolver.created["tags"], "createdPeople": resolver.created["people"],
        "issues": parsed["issues"],
    }


def _update_existing(conn, resolver: _Resolver, t: CsvTransaction, matched_id: int, existing_row: dict | None) -> bool:
    """دسته/شخص را فقط در صورت وجود مقدار در فایل عوض می‌کند (خالی = دست‌نخورده)؛ برچسب‌ها فقط اضافه می‌شوند."""
    if existing_row is None:
        return False
    changed = False
    cat_id = resolver.category_path(t.category_path) if t.category_path else None
    if cat_id is None and t.legacy_category_id and not t.category_path:
        cat_id, _ = _resolve_legacy(conn, t)
    if cat_id and cat_id != existing_row["category_id"]:
        conn.execute("UPDATE transactions SET category_id = ?, updated_at = datetime('now') WHERE id = ?", (cat_id, matched_id))
        existing_row["category_id"] = cat_id
        changed = True
    person_id = resolver.person(t.person_name) if t.person_name else None
    if person_id is None and t.legacy_person_id and not t.person_name:
        _, person_id = _resolve_legacy(conn, t)
    if person_id and person_id != existing_row["person_id"]:
        conn.execute("UPDATE transactions SET person_id = ?, updated_at = datetime('now') WHERE id = ?", (person_id, matched_id))
        existing_row["person_id"] = person_id
        changed = True
    for name in t.tags:
        tag_id = resolver.tag(name)
        cur = conn.execute("INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (matched_id, tag_id))
        if cur.rowcount:
            changed = True
    return changed


# ───────────────────────────── فایل دسته‌بندی‌ها و برچسب‌ها ─────────────────────────────
def import_taxonomy_csv(conn: sqlite3.Connection, content: bytes) -> dict:
    """
    دسته‌بندی‌ها و برچسب‌های ناموجود را می‌سازد (با ساختار والد/فرزند) و رنگ/آیکن را برای موارد موجود
    به‌روز می‌کند. چیزی حذف نمی‌شود. کل عملیات اتمیک است.
    """
    columns, rows = _read_table(content)
    if not ({"kind", "name"} <= set(columns)):
        raise CsvFormatError("ستون‌های «kind» و «name» در فایل یافت نشد")

    resolver = _Resolver(conn, dry_run=False)
    updated = 0
    issues = []
    try:
        for row_no, r in rows:
            kind, name = normalize_text(r.get("kind", "")), r.get("name", "")
            if kind in ("category", "دستهبندی", "دسته", "دسته‌بندی"):
                kind = "category"
            elif kind in ("tag", "برچسب"):
                kind = "tag"
            else:
                issues.append({"row_number": row_no, "rowNumber": row_no, "message": f"مقدار «kind» نامعتبر است: «{r.get('kind', '')}»"})
                continue
            if not name:
                issues.append({"row_number": row_no, "rowNumber": row_no, "message": "نام خالی است"})
                continue
            color, icon = r.get("color") or None, r.get("icon") or None
            if kind == "category":
                cid = resolver.category_path(name)
                row = conn.execute("SELECT color, icon FROM categories WHERE id = ?", (cid,)).fetchone()
                if (color and color != row["color"]) or (icon and icon != row["icon"]):
                    conn.execute("UPDATE categories SET color = COALESCE(?, color), icon = COALESCE(?, icon) WHERE id = ?",
                                 (color, icon, cid))
                    updated += 1
            else:
                tid = resolver.tag(name)
                row = conn.execute("SELECT color FROM tags WHERE id = ?", (tid,)).fetchone()
                if color and color != row["color"]:
                    conn.execute("UPDATE tags SET color = ? WHERE id = ?", (color, tid))
                    updated += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {
        "createdCategories": resolver.created["categories"], "createdTags": resolver.created["tags"],
        "updated": updated, "total": len(rows), "issues": issues,
    }
