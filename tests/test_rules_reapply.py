"""
رگرسیون‌های «قوانین خودکار»:
1) قانون کاربر (مثلاً برچسب دیجیکالا بر اساس شماره پایانه) نباید توسط قوانین پیش‌فرض «سایه» شود.
2) مقدار قانون با ارقام فارسی/انگلیسی، صفر ابتدایی و چند گزینه (OR) درست تطبیق شود.
3) endpoint جدید «اعمال مجدد روی همه تراکنش‌ها».
4) «بازپردازش توضیحات» با force روی همه تراکنش‌ها اعمال شود، نه فقط ردیف‌های خالی.
"""
import json
import pytest
from fastapi.testclient import TestClient
from app.db import open_db
from app.main import create_app
from app.importers.import_orchestrator import run_import, undo_import_batch
from app.lib.duplicate_detection import NormalizedTransaction
from app.lib.rules_engine import _condition_matches


@pytest.fixture
def conn():
    c = open_db(":memory:")
    yield c
    c.close()


@pytest.fixture
def account_id(conn):
    cur = conn.execute("INSERT INTO accounts (name, type, initial_balance) VALUES ('حساب','bank',0)")
    conn.commit()
    return cur.lastrowid


def make_txn(account_id, doc, description, **kw):
    base = dict(account_id=account_id, transaction_date="2026-01-01", transaction_time="10:00:00", amount=100000,
                type="expense", description=description, document_number=doc, balance_after=1,
                source_row_number=1, raw_transaction_type="خرید اینترنتی")
    base.update(kw)
    return NormalizedTransaction(**base)


def add_tag(conn, name):
    conn.execute("INSERT INTO tags (name) VALUES (?)", (name,))
    conn.commit()
    return conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()["id"]


def add_rule(conn, name, field, value, actions, op="contains", auto_apply=1, active=1):
    conn.execute(
        "INSERT INTO rules (name, condition, actions, active, auto_apply) VALUES (?, ?, ?, ?, ?)",
        (name, json.dumps({"field": field, "op": op, "value": value}), json.dumps(actions), active, auto_apply),
    )
    conn.commit()


def tags_of(conn, doc):
    return {r["name"] for r in conn.execute(
        "SELECT tg.name FROM tags tg JOIN transaction_tags tt ON tt.tag_id = tg.id "
        "JOIN transactions t ON t.id = tt.transaction_id WHERE t.document_number = ?", (doc,))}


def category_name(conn, doc):
    row = conn.execute(
        "SELECT c.name FROM transactions t LEFT JOIN categories c ON c.id = t.category_id WHERE t.document_number = ?",
        (doc,)).fetchone()
    return row["name"]


# ---------- ۱) سایه‌شدن قانون کاربر توسط قوانین پیش‌فرض ----------
def test_user_tag_rule_is_not_shadowed_by_seeded_default_rule_on_import(conn, account_id):
    tag = add_tag(conn, "دیجیکالا")
    add_rule(conn, "دیجیکالا", "description", "82000221 | 08975292", {"tagIds": [tag]})
    txns = [
        make_txn(account_id, "A", "خرید اینترنتی پایانه 82000221"),
        make_txn(account_id, "B", "خرید اینترنتی پایانه 08975292"),
        make_txn(account_id, "C", "خرید اینترنتی پایانه 11111111"),
    ]
    summary = run_import(conn, account_id, "x.xlsx", "generic-bank-xlsx", txns, [], apply_rules=True)

    assert tags_of(conn, "A") == {"دیجیکالا"}
    assert tags_of(conn, "B") == {"دیجیکالا"}
    assert tags_of(conn, "C") == set()
    # قانون پیش‌فرض (دسته‌بندی بر اساس نوع تراکنش بانک) هم همچنان اعمال می‌شود
    assert category_name(conn, "A") == "خرید آنلاین"
    assert category_name(conn, "C") == "خرید آنلاین"
    assert summary["rules_applied_count"] == 3 and summary["rulesApplied"] == 3
    assert summary["newCount"] == 3


def test_newer_user_category_overrides_older_default_but_tags_merge(conn, account_id):
    cat = conn.execute("INSERT INTO categories (name) VALUES ('لوازم دیجیتال')").lastrowid
    tag = add_tag(conn, "دیجیکالا")
    add_rule(conn, "دیجیکالا", "description", "82000221", {"categoryId": cat, "tagIds": [tag]})
    run_import(conn, account_id, "x.xlsx", "g", [make_txn(account_id, "A", "پایانه 82000221")], [], apply_rules=True)
    assert category_name(conn, "A") == "لوازم دیجیتال"
    assert tags_of(conn, "A") == {"دیجیکالا"}


def test_suggest_only_rule_is_not_applied(conn, account_id):
    tag = add_tag(conn, "پیشنهادی")
    add_rule(conn, "فقط پیشنهاد", "description", "82000221", {"tagIds": [tag]}, auto_apply=0)
    run_import(conn, account_id, "x.xlsx", "g", [make_txn(account_id, "A", "پایانه 82000221")], [], apply_rules=True)
    assert tags_of(conn, "A") == set()


def test_inactive_rule_is_ignored(conn, account_id):
    tag = add_tag(conn, "غیرفعال")
    add_rule(conn, "غیرفعال", "description", "82000221", {"tagIds": [tag]}, active=0)
    run_import(conn, account_id, "x.xlsx", "g", [make_txn(account_id, "A", "پایانه 82000221")], [], apply_rules=True)
    assert tags_of(conn, "A") == set()


def test_import_with_rules_still_rolls_back_atomically(conn, account_id):
    tag = add_tag(conn, "دیجیکالا")
    add_rule(conn, "دیجیکالا", "description", "82000221", {"tagIds": [tag]})
    good = make_txn(account_id, "A", "پایانه 82000221")
    bad = make_txn(99999, "B", "پایانه 82000221")  # FK نامعتبر → کل import باید rollback شود
    with pytest.raises(Exception):
        run_import(conn, account_id, "x.xlsx", "g", [good, bad], [], apply_rules=True)
    assert conn.execute("SELECT COUNT(*) c FROM transactions").fetchone()["c"] == 0
    assert conn.execute("SELECT COUNT(*) c FROM transaction_tags").fetchone()["c"] == 0


# ---------- ۲) تطبیق شرط ----------
@pytest.mark.parametrize("value, description, expected", [
    ("82000221", "پایانه ۸۲۰۰۰۲۲۱", True),            # ارقام فارسی در شرح، انگلیسی در قانون
    ("۸۲۰۰۰۲۲۱", "پایانه 82000221", True),            # برعکس
    ("٨٢٠٠٠٢٢١", "پایانه 82000221", True),            # ارقام عربی-هندی
    ("08975292", "پایانه 8975292", True),             # صفر ابتدایی اختیاری
    ("8975292", "پایانه 08975292", True),
    ("82000221", "کارت 6037982000221999", False),     # داخل عدد بلندتر نباید پیدا شود
    ("82000221 یا 08975292", "پایانه 8975292", True),  # «یا»
    ("82000221 or 08975292", "پایانه 8975292", True),
    ("82000221،08975292", "پایانه 8975292", True),     # ویرگول فارسی
    ("82000221\n08975292", "پایانه 8975292", True),    # خط جدید
    ("دیجی‌کالا", "خرید از دیجی کالا", False),          # نیم‌فاصله حذف می‌شود ولی فاصله عادی نه
    ("دیجی‌کالا", "خرید از دیجی‌کالا", True),
    ("عليرضا", "خرید از علیرضا", True),                # ي عربی
])
def test_description_contains_matching(value, description, expected):
    cond = {"field": "description", "op": "contains", "value": value}
    assert _condition_matches(cond, {"description": description}) is expected


def test_amount_rule_from_ui_form_works():
    # فرم UI همیشه op=contains می‌فرستد؛ برای مبلغ باید «برابر با» عمل کند
    assert _condition_matches({"field": "amount", "op": "contains", "value": "50,000"}, {"amount": 50000})
    assert _condition_matches({"field": "amount", "op": "equals", "value": "۵۰۰۰۰"}, {"amount": 50000})
    assert not _condition_matches({"field": "amount", "op": "contains", "value": "50000"}, {"amount": 60000})
    assert _condition_matches({"field": "amount", "op": "gt", "value": "1000"}, {"amount": 50000})


def test_raw_transaction_type_equals():
    cond = {"field": "rawTransactionType", "op": "equals", "value": "خرید اینترنتی"}
    assert _condition_matches(cond, {"raw_transaction_type": "خرید اینترنتی"})
    assert not _condition_matches(cond, {"raw_transaction_type": "قبض"})
    assert not _condition_matches(cond, {"raw_transaction_type": None})


# ---------- ۳) endpoint اعمال مجدد روی همه ----------
@pytest.fixture
def client():
    db = open_db(":memory:")
    return TestClient(create_app(db))


def _setup_api(client):
    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()["id"]
    tag = client.post("/api/tags", json={"name": "دیجیکالا"}).json()["id"]
    cat_manual = client.post("/api/categories", json={"name": "دستی من"}).json()["id"]
    ids = {}
    for key, desc in {"digi": "پایانه 82000221", "digi2": "پایانه ۰۸۹۷۵۲۹۲", "other": "پایانه 5555"}.items():
        ids[key] = client.post("/api/transactions", json={
            "accountId": acc, "transactionDate": "2026-01-01", "amount": 1000, "type": "expense",
            "description": desc, "categoryId": cat_manual}).json()["id"]
        # همه تراکنش‌ها از قبل «دسته» دارند و یکی هم تگ دارد → run-on-uncategorized آن‌ها را نمی‌گرفت
        client.put(f"/api/transactions/{ids[key]}", json={"rawTransactionType": "خرید اینترنتی"})
    client.post("/api/rules", json={
        "name": "دیجیکالا", "condition": {"field": "description", "op": "contains", "value": "82000221 یا 08975292"},
        "actions": {"tagIds": [tag]}, "autoApply": True})
    return acc, tag, cat_manual, ids


def test_run_on_all_reapplies_to_already_categorized_transactions(client):
    _, tag, _, ids = _setup_api(client)
    # با گزینه قدیمی «بدون دسته» این تراکنش‌ها (چون دسته دارند ولی تگ ندارند) شاید گرفته شوند؛ اینجا کل مسیر جدید را می‌سنجیم
    res = client.post("/api/rules/run-on-all", json={})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 3
    assert body["matched"] == 3          # هر ۳ تراکنش حداقل با قانون پیش‌فرض «خرید اینترنتی» منطبق‌اند
    assert body["changed"] == 3

    def tag_names(key):
        return {t["name"] for t in client.get(f"/api/transactions/{ids[key]}").json()["tags"]}
    assert tag_names("digi") == {"دیجیکالا"}
    assert tag_names("digi2") == {"دیجیکالا"}
    assert tag_names("other") == set()


def test_run_on_all_is_idempotent(client):
    _setup_api(client)
    client.post("/api/rules/run-on-all", json={})
    second = client.post("/api/rules/run-on-all", json={}).json()
    assert second["changed"] == 0


def test_run_on_all_overwrite_false_keeps_existing_category(client):
    _, _, cat_manual, ids = _setup_api(client)
    client.post("/api/rules/run-on-all", json={"overwriteCategory": False})
    txn = client.get(f"/api/transactions/{ids['digi']}").json()
    assert txn["category_id"] == cat_manual
    assert {t["name"] for t in txn["tags"]} == {"دیجیکالا"}   # برچسب ولی اضافه می‌شود


def test_run_on_all_overwrite_true_applies_default_category(client):
    _, _, cat_manual, ids = _setup_api(client)
    client.post("/api/rules/run-on-all", json={"overwriteCategory": True})
    txn = client.get(f"/api/transactions/{ids['digi']}").json()
    assert txn["category_id"] != cat_manual


def test_run_on_all_works_without_body(client):
    _setup_api(client)
    assert client.post("/api/rules/run-on-all").status_code == 200


def test_run_on_uncategorized_now_merges_all_matching_rules(client):
    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()["id"]
    tag = client.post("/api/tags", json={"name": "دیجیکالا"}).json()["id"]
    tid = client.post("/api/transactions", json={
        "accountId": acc, "transactionDate": "2026-01-01", "amount": 1000, "type": "expense",
        "description": "پایانه 82000221"}).json()["id"]
    client.put(f"/api/transactions/{tid}", json={"rawTransactionType": "خرید اینترنتی"})
    client.post("/api/rules", json={"name": "دیجیکالا", "condition": {"field": "description", "op": "contains", "value": "82000221"},
                                     "actions": {"tagIds": [tag]}, "autoApply": True})
    res = client.post("/api/rules/run-on-uncategorized").json()
    assert len(res["applied"]) == 1
    txn = client.get(f"/api/transactions/{tid}").json()
    assert txn["category_id"] is not None
    assert {t["name"] for t in txn["tags"]} == {"دیجیکالا"}


# ---------- ۴) بازپردازش توضیحات ----------
def _seed_reparse(client):
    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()["id"]
    # تراکنش‌هایی که از قبل یک فیلد استخراج‌شده دارند (مثل حالتی که ۵۰۳ تای دیگر را نادیده می‌گرفت)
    a = client.post("/api/transactions", json={
        "accountId": acc, "transactionDate": "2026-01-01", "amount": 1000, "type": "expense",
        "description": "انتقال به آقای علی رضایی بانک ملت", "bankName": "غلط"}).json()["id"]
    b = client.post("/api/transactions", json={
        "accountId": acc, "transactionDate": "2026-01-01", "amount": 1000, "type": "expense",
        "description": "چیز بدون الگو", "counterparty": "ورود دستی"}).json()["id"]
    return a, b


def test_reparse_default_skips_rows_with_existing_fields(client):
    a, _ = _seed_reparse(client)
    res = client.post("/api/transactions/reparse-descriptions", json={}).json()
    assert res["skipped"] == 2 and res["updated"] == 0
    assert client.get(f"/api/transactions/{a}").json()["bank_name"] == "غلط"


def test_reparse_force_processes_all_transactions(client):
    a, b = _seed_reparse(client)
    res = client.post("/api/transactions/reparse-descriptions", json={"force": True}).json()
    assert res["total"] == 2 and res["processed"] == 2 and res["skipped"] == 0
    assert client.get(f"/api/transactions/{a}").json()["bank_name"] == "ملت"       # مقدار غلط اصلاح شد
    # مقدار دستی که parser چیزی برایش پیدا نمی‌کند پاک نمی‌شود
    assert client.get(f"/api/transactions/{b}").json()["counterparty"] == "ورود دستی"
