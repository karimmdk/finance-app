"""
خروجی CSV باید «دوطرفه» باشد: هر چه خروجی گرفته شود (با همه دسته‌بندی‌ها، برچسب‌ها، اشخاص، حساب‌ها) دوباره
در این برنامه (حتی روی دیتابیس تازه) درون‌ریزی شود و همان داده را بسازد.
"""
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import open_db
from app.main import create_app
from app.lib import csv_exchange
from app.lib.csv_exchange import CsvFormatError

REAL_XLSX = Path(__file__).parent / "fixtures" / "real-statement.xlsx"


def make_client():
    db = open_db(":memory:")
    return TestClient(create_app(db, static_dir=None)), db


def upload(client, path, content: bytes, name: str, **data):
    return client.post(path, files={"file": (name, content)}, data={k: str(v) for k, v in data.items()})


def import_csv(client, content: bytes, account_id, name="x.csv", apply_rules=False, update_existing=True, commit=True):
    data = {"accountId": account_id, "applyRules": str(apply_rules).lower(), "updateExisting": str(update_existing).lower()}
    return upload(client, "/api/transactions/import/commit" if commit else "/api/transactions/import/preview", content, name, **data)


def snapshot(db):
    """محتوای معنایی تراکنش‌ها بدون وابستگی به شناسه‌های عددی — برای مقایسه دو دیتابیس."""
    paths = csv_exchange._category_paths(db)
    tags = {}
    for r in db.execute("SELECT tt.transaction_id t, tg.name n FROM transaction_tags tt JOIN tags tg ON tg.id = tt.tag_id"):
        tags.setdefault(r["t"], []).append(r["n"])
    out = []
    for t in db.execute("""SELECT t.*, a.name an, p.name pn FROM transactions t JOIN accounts a ON a.id = t.account_id
                           LEFT JOIN people p ON p.id = t.person_id"""):
        out.append((
            t["an"], t["transaction_date"], t["transaction_time"], t["type"], t["amount"], t["balance_after"],
            t["description"], t["document_number"], t["counterparty"], t["card_number"], t["iban"], t["bank_name"],
            t["reason"], t["raw_transaction_type"], paths.get(t["category_id"]) if t["category_id"] else None,
            t["pn"], tuple(sorted(tags.get(t["id"], []))), t["notes"], t["excluded_from_analysis"], t["transfer_id"],
        ))
    return sorted(out, key=lambda x: tuple("" if v is None else str(v) for v in x))


def seed_real_data(client, db):
    """صورتحساب واقعی + دسته‌بندی سلسله‌مراتبی + برچسب‌ها + شخص + یادداشت + exclude روی چند تراکنش."""
    acc = client.post("/api/accounts", json={"name": "پاسارگاد", "type": "bank", "initialBalance": 0}).json()["id"]
    r = upload(client, "/api/transactions/import/commit", REAL_XLSX.read_bytes(), "s.xlsx", accountId=acc, applyRules="true")
    assert r.status_code == 201 and r.json()["newCount"] == 90

    parent = client.post("/api/categories", json={"name": "خرید"}).json()["id"]
    child = client.post("/api/categories", json={"name": "دیجیتال", "parentId": parent, "color": "#3366ff"}).json()["id"]
    client.post("/api/categories", json={"name": "بدون تراکنش"})  # استفاده‌نشده
    t_digi = client.post("/api/tags", json={"name": "دیجیکالا", "color": "#ff0000"}).json()["id"]
    t_weird = client.post("/api/tags", json={"name": "الف|ب، ج;د\\ه"}).json()["id"]  # نام با همه جداکننده‌ها
    client.post("/api/tags", json={"name": "برچسب بی‌استفاده"})
    person = client.post("/api/people", json={"name": "علی رضایی"}).json()["id"]

    ids = [r["id"] for r in db.execute("SELECT id FROM transactions ORDER BY id LIMIT 6")]
    client.put(f"/api/transactions/{ids[0]}", json={"categoryId": child, "personId": person, "notes": 'یادداشت با "نقل‌قول"، ویرگول\nو خط جدید'})
    for tid, tags in ((ids[0], [t_digi, t_weird]), (ids[1], [t_digi]), (ids[2], [t_weird])):
        for tg in tags:
            db.execute("INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (tid, tg))
    db.execute("UPDATE transactions SET description = ?, excluded_from_analysis = 1 WHERE id = ?", ("=SUM(A1:A2) خطرناک", ids[3]))
    db.execute("UPDATE transactions SET description = ? WHERE id = ?", ("-منفی شروع می‌شود", ids[4]))
    db.commit()
    return acc


# ─────────────────────────── مهم‌ترین تست: چرخه کامل خروجی → ورودی ───────────────────────────
def test_full_round_trip_into_fresh_database_preserves_everything():
    src, src_db = make_client()
    seed_real_data(src, src_db)
    exported = src.get("/api/backup/transactions.csv")
    assert exported.status_code == 200
    csv_bytes = exported.content

    dst, dst_db = make_client()
    fallback = dst.post("/api/accounts", json={"name": "دیگر", "type": "bank", "initialBalance": 0}).json()["id"]

    preview = import_csv(dst, csv_bytes, fallback, commit=False).json()
    assert preview["kind"] == "transactions_csv"
    assert preview["summary"]["total"] == 90 and preview["summary"]["new"] == 90
    assert not preview["issues"]
    notes = " ".join(preview["summary"]["notes"])
    assert "پاسارگاد" in notes and "دیجیکالا" in notes   # حساب/برچسب جدید اعلام می‌شود

    r = import_csv(dst, csv_bytes, fallback)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["newCount"] == 90 and body["createdAccounts"] == 1

    assert snapshot(dst_db) == snapshot(src_db)   # همه فیلدها، دسته (مسیر کامل)، شخص، برچسب‌ها، یادداشت، exclude، ...
    # ساختار دسته‌بندی سلسله‌مراتبی و رنگ تگ بازسازی شده (رنگ در فایل تراکنش‌ها نیست؛ فقط ساختار)
    assert dst_db.execute("SELECT COUNT(*) FROM categories c JOIN categories p ON p.id = c.parent_id WHERE c.name='دیجیتال' AND p.name='خرید'").fetchone()[0] == 1


def test_reimport_into_same_database_is_idempotent():
    client, db = make_client()
    acc = seed_real_data(client, db)
    before = snapshot(db)
    csv_bytes = client.get("/api/backup/transactions.csv").content

    p = import_csv(client, csv_bytes, acc, commit=False).json()
    assert p["summary"]["definiteDuplicate"] == 90 and p["summary"]["new"] == 0
    assert p["summary"]["taxonomyUpdates"] == 0

    r = import_csv(client, csv_bytes, acc).json()
    assert r["newCount"] == 0 and r["updatedCount"] == 0 and r["definiteDuplicateCount"] == 90
    assert snapshot(db) == before


def test_edited_csv_updates_categories_and_tags_of_existing_transactions():
    client, db = make_client()
    acc = client.post("/api/accounts", json={"name": "پاسارگاد", "type": "bank", "initialBalance": 0}).json()["id"]
    upload(client, "/api/transactions/import/commit", REAL_XLSX.read_bytes(), "s.xlsx", accountId=acc)
    text = client.get("/api/backup/transactions.csv").content.decode("utf-8-sig")

    import csv as _csv
    rows = list(_csv.reader(io.StringIO(text)))
    header = rows[0]
    ci, ti = header.index("category"), header.index("tags")
    di = header.index("document_number")
    target = rows[1]
    target[ci], target[ti] = "هزینه‌ها > قبوض", "مهم | بررسی‌شود"
    out = io.StringIO(); _csv.writer(out).writerows(rows)
    edited = ("\ufeff" + out.getvalue()).encode("utf-8")

    p = import_csv(client, edited, acc, commit=False).json()
    assert p["summary"]["taxonomyUpdates"] == 1
    flagged = [x for x in p["preview"] if x["taxonomyChange"]]
    assert len(flagged) == 1

    # با غیرفعال‌کردن گزینه، تراکنش موجود دست‌نخورده می‌ماند
    r = import_csv(client, edited, acc, update_existing=False).json()
    assert r["updatedCount"] == 0
    assert db.execute("SELECT COUNT(*) FROM tags WHERE name='مهم'").fetchone()[0] == 0

    r = import_csv(client, edited, acc, update_existing=True).json()
    assert r["updatedCount"] == 1 and r["newCount"] == 0 and r["createdCategories"] == 2 and r["createdTags"] == 2
    row = db.execute("SELECT id, category_id FROM transactions WHERE document_number = ? AND amount = ?",
                     (target[di], int(target[header.index('amount')]))).fetchone()
    tags = {x["name"] for x in db.execute("SELECT tg.name FROM tags tg JOIN transaction_tags tt ON tt.tag_id = tg.id WHERE tt.transaction_id = ?", (row["id"],))}
    assert tags == {"مهم", "بررسی‌شود"}
    assert csv_exchange._category_paths(db)[row["category_id"]] == "هزینه‌ها > قبوض"
    # دوباره اجرا: بدون تغییر
    assert import_csv(client, edited, acc).json()["updatedCount"] == 0


def test_blank_category_in_file_does_not_erase_existing_category():
    client, db = make_client()
    acc = client.post("/api/accounts", json={"name": "A", "type": "bank", "initialBalance": 0}).json()["id"]
    cat = client.post("/api/categories", json={"name": "غذا"}).json()["id"]
    tid = client.post("/api/transactions", json={"accountId": acc, "transactionDate": "2026-01-01", "amount": 5000,
                                                  "type": "expense", "description": "x", "categoryId": cat}).json()["id"]
    csv_bytes = ("transaction_date,amount,type,description,account,category\n"
                 "2026-01-01,5000,expense,x,A,\n").encode("utf-8")
    r = import_csv(client, csv_bytes, acc).json()
    assert r["definiteDuplicateCount"] == 1 and r["updatedCount"] == 0
    assert db.execute("SELECT category_id FROM transactions WHERE id = ?", (tid,)).fetchone()[0] == cat


# ─────────────────────────── فایل دسته‌بندی‌ها و برچسب‌ها ───────────────────────────
def test_taxonomy_export_contains_all_categories_and_tags_including_unused_and_roundtrips():
    src, src_db = make_client()
    seed_real_data(src, src_db)
    content = src.get("/api/backup/categories-tags.csv").content
    text = content.decode("utf-8-sig")
    assert "بدون تراکنش" in text and "برچسب بی‌استفاده" in text and "خرید > دیجیتال" in text
    assert "#3366ff" in text and "#ff0000" in text

    dst, dst_db = make_client()
    # دیتابیس مقصد «تازه» است ولی migration دسته‌های پیش‌فرض را دارد؛ فقط ناموجودها ساخته می‌شوند
    r = upload(dst, "/api/backup/import-categories-tags", content, "t.csv")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["createdTags"] >= 3
    src_paths = set(csv_exchange._category_paths(src_db).values())
    dst_paths = set(csv_exchange._category_paths(dst_db).values())
    assert src_paths <= dst_paths
    src_tags = {x["name"] for x in src_db.execute("SELECT name FROM tags")}
    dst_tags = {x["name"] for x in dst_db.execute("SELECT name FROM tags")}
    assert src_tags <= dst_tags
    assert dst_db.execute("SELECT color FROM tags WHERE name='دیجیکالا'").fetchone()[0] == "#ff0000"
    assert dst_db.execute("SELECT color FROM categories WHERE name='دیجیتال'").fetchone()[0] == "#3366ff"
    # اجرای دوباره: چیزی ساخته یا عوض نمی‌شود
    again = upload(dst, "/api/backup/import-categories-tags", content, "t.csv").json()
    assert again["createdCategories"] == 0 and again["createdTags"] == 0 and again["updated"] == 0


def test_wrong_file_kind_gives_clear_error():
    client, db = make_client()
    acc = client.post("/api/accounts", json={"name": "A", "type": "bank", "initialBalance": 0}).json()["id"]
    tax = client.get("/api/backup/categories-tags.csv").content
    r = import_csv(client, tax, acc)
    assert r.status_code == 400 and "دسته‌بندی/برچسب" in r.json()["error"]
    txn = client.get("/api/backup/transactions.csv").content
    r2 = upload(client, "/api/backup/import-categories-tags", txn, "t.csv")
    assert r2.status_code == 400 and "تراکنش" in r2.json()["error"]
    r3 = import_csv(client, "a,b\n1,2\n".encode(), acc)
    assert r3.status_code == 400


# ─────────────────────────── مقاومت در برابر Excel و فایل دست‌ساز ───────────────────────────
def test_formula_injection_is_neutralised_in_export_and_restored_on_import():
    client, db = make_client()
    seed_real_data(client, db)
    text = client.get("/api/backup/transactions.csv").content.decode("utf-8-sig")
    assert "'=SUM(A1:A2)" in text and "'-منفی" in text
    # هیچ سلولی نباید مستقیماً با = یا @ شروع شود
    import csv as _csv
    for row in list(_csv.reader(io.StringIO(text)))[1:]:
        for cell in row:
            assert not cell.startswith(("=", "@", "+")), cell


@pytest.mark.parametrize("delimiter, encoding", [(",", "utf-8-sig"), (";", "utf-8-sig"), ("\t", "utf-8"), (";", "cp1256")])
def test_delimiters_and_encodings_from_excel(delimiter, encoding):
    client, db = make_client()
    acc = client.post("/api/accounts", json={"name": "حساب من", "type": "bank", "initialBalance": 0}).json()["id"]
    rows = [["تاریخ", "مبلغ", "نوع", "شرح", "دسته‌بندی", "برچسب‌ها"],
            ["1405/06/01", "5,863,832", "هزینه", "خرید 82000221", "خرید > دیجیتال", "دیجیکالا"]]
    import csv as _csv
    buf = io.StringIO()
    _csv.writer(buf, delimiter=delimiter).writerows(rows)      # مثل Excel: سلول‌های دارای جداکننده quote می‌شوند
    text = buf.getvalue()
    if encoding == "cp1256":
        text = text.translate(str.maketrans({"ی": "ي", "ک": "ك"}))   # Excel ویندوز فارسی «ی/ک» را به حروف عربی تبدیل می‌کند
    content = text.encode(encoding)
    r = import_csv(client, content, acc)
    assert r.status_code == 201, r.text
    row = db.execute("SELECT * FROM transactions").fetchone()
    assert row["amount"] == 5863832 and row["type"] == "expense"
    assert row["transaction_date"] == "2026-08-23"          # ۱۴۰۵/۰۶/۰۱ شمسی
    assert row["description"] == "خرید 82000221"
    assert row["account_id"] == acc                            # بدون ستون حساب ← حساب انتخاب‌شده
    assert csv_exchange._category_paths(db)[row["category_id"]] == "خرید > دیجیتال"


def test_persian_digits_and_signed_amounts_without_type():
    client, db = make_client()
    acc = client.post("/api/accounts", json={"name": "A", "type": "bank", "initialBalance": 0}).json()["id"]
    content = "transaction_date,amount,description\n۱۴۰۵/۰۶/۰۱,\"۱٬۲۳۴٬۵۶۷\",در\n2026-08-24,-500,برداشت\n".encode("utf-8")
    assert import_csv(client, content, acc).status_code == 201
    rows = {r["description"]: r for r in db.execute("SELECT * FROM transactions")}
    assert rows["در"]["amount"] == 1234567 and rows["در"]["type"] == "income"
    assert rows["برداشت"]["amount"] == 500 and rows["برداشت"]["type"] == "expense"


def test_excel_scientific_notation_ids_are_flagged_not_imported():
    client, db = make_client()
    acc = client.post("/api/accounts", json={"name": "A", "type": "bank", "initialBalance": 0}).json()["id"]
    content = "transaction_date,amount,type,document_number,card_number\n2026-01-01,1000,expense,1.40543E+13,6.03799E+15\n".encode()
    p = import_csv(client, content, acc, commit=False).json()
    assert len(p["issues"]) == 2 and all(i["rowNumber"] == 2 for i in p["issues"])
    assert import_csv(client, content, acc).status_code == 201
    row = db.execute("SELECT document_number, card_number FROM transactions").fetchone()
    assert row["document_number"] is None and row["card_number"] is None


def test_bad_rows_are_reported_and_skipped():
    client, db = make_client()
    acc = client.post("/api/accounts", json={"name": "A", "type": "bank", "initialBalance": 0}).json()["id"]
    content = ("transaction_date,amount,type\n"
               "2026-01-01,1000,expense\n"
               "not-a-date,1000,expense\n"
               "2026-01-02,abc,expense\n"
               "2026-01-03,1000,weird\n"
               "2026-01-04,0,expense\n"
               ",,\n").encode()
    p = import_csv(client, content, acc, commit=False).json()
    assert p["summary"]["total"] == 1
    assert sorted(i["rowNumber"] for i in p["issues"]) == [3, 4, 5, 6]


def test_legacy_old_export_format_still_importable():
    client, db = make_client()
    acc = client.post("/api/accounts", json={"name": "A", "type": "bank", "initialBalance": 0}).json()["id"]
    cat = client.post("/api/categories", json={"name": "غذا"}).json()["id"]
    old = (f"id,account_id,transaction_date,amount,type,description,document_number,category_id,person_id\n"
           f"7,{acc},2026-01-01,5000,expense,ناهار,D1,{cat},\n"
           f"8,999,2026-01-02,6000,expense,شام,D2,12345,\n").encode()
    p = import_csv(client, old, acc, commit=False).json()
    assert any("قدیمی" in n for n in p["summary"]["notes"])
    assert import_csv(client, old, acc).status_code == 201
    rows = {r["description"]: r for r in db.execute("SELECT * FROM transactions")}
    assert rows["ناهار"]["category_id"] == cat
    assert rows["شام"]["category_id"] is None and rows["شام"]["account_id"] == acc   # شناسه ناموجود ← نادیده، حساب پیش‌فرض


def test_rules_apply_only_to_rows_without_category_or_tags_in_file():
    client, db = make_client()
    acc = client.post("/api/accounts", json={"name": "A", "type": "bank", "initialBalance": 0}).json()["id"]
    tag = client.post("/api/tags", json={"name": "دیجیکالا"}).json()["id"]
    client.post("/api/rules", json={"name": "دیجیکالا", "condition": {"field": "description", "op": "contains", "value": "82000221"},
                                     "actions": {"tagIds": [tag]}, "autoApply": True})
    content = ("transaction_date,amount,type,description,category,tags\n"
               "2026-01-01,1000,expense,پایانه 82000221,,\n"
               "2026-01-02,2000,expense,پایانه 82000221,دستی,\n"
               "2026-01-03,3000,expense,پایانه 82000221,,برچسب من\n").encode()
    r = import_csv(client, content, acc, apply_rules=True).json()
    assert r["rulesApplied"] == 1
    def tags_for(amount):
        return {x["name"] for x in db.execute("SELECT tg.name FROM tags tg JOIN transaction_tags tt ON tt.tag_id = tg.id JOIN transactions t ON t.id = tt.transaction_id WHERE t.amount = ?", (amount,))}
    assert tags_for(1000) == {"دیجیکالا"} and tags_for(2000) == set() and tags_for(3000) == {"برچسب من"}


def test_csv_import_is_atomic_on_failure(monkeypatch):
    client, db = make_client()
    acc = client.post("/api/accounts", json={"name": "A", "type": "bank", "initialBalance": 0}).json()["id"]
    content = ("account,transaction_date,amount,type,category,tags\n"
               "حساب تازه,2026-01-01,1000,expense,دسته تازه,برچسب تازه\n"
               "حساب تازه,2026-01-02,2000,expense,دسته تازه,برچسب تازه\n").encode()
    calls = {"n": 0}
    real = csv_exchange.parse_transaction_description
    def boom(desc):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("خطای مصنوعی")
        return real(desc)
    monkeypatch.setattr(csv_exchange, "parse_transaction_description", boom)
    r = import_csv(client, content, acc)
    assert r.status_code == 500 and "rollback" in r.json()["error"]
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM accounts WHERE name='حساب تازه'").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM tags WHERE name='برچسب تازه'").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM categories WHERE name='دسته تازه'").fetchone()[0] == 0


def test_xlsx_import_still_works_after_csv_support():
    client, db = make_client()
    acc = client.post("/api/accounts", json={"name": "A", "type": "bank", "initialBalance": 0}).json()["id"]
    p = upload(client, "/api/transactions/import/preview", REAL_XLSX.read_bytes(), "s.xlsx", accountId=acc).json()
    assert p["summary"]["total"] == 90 and "rowNumber" in p["issues"][0]
    assert all(i["message"] != "تاریخ تراکنش خالی است — ردیف نادیده گرفته شد" for i in p["issues"])   # فوتر صفحه
