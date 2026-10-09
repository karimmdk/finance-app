import pytest
from fastapi.testclient import TestClient
from app.db import open_db
from app.main import create_app


@pytest.fixture
def client():
    db = open_db(":memory:")
    app = create_app(db)
    return TestClient(app)


def test_recurring_not_swallowed_by_id_route(client):
    res = client.get("/api/transactions/recurring")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_anomalies_not_swallowed_by_id_route(client):
    res = client.get("/api/transactions/anomalies")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_get_transaction_by_real_id_still_works(client):
    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()
    txn = client.post("/api/transactions", json={
        "accountId": acc["id"], "transactionDate": "2026-01-01", "amount": 1000, "type": "expense"
    }).json()
    res = client.get(f"/api/transactions/{txn['id']}")
    assert res.status_code == 200
    assert res.json()["id"] == txn["id"]


def test_nonexistent_id_returns_404_not_confused_with_named_routes(client):
    res = client.get("/api/transactions/999999")
    assert res.status_code == 404


def test_bulk_update_applies_category(client):
    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()
    cat = client.post("/api/categories", json={"name": "خوراک"}).json()
    t1 = client.post("/api/transactions", json={"accountId": acc["id"], "transactionDate": "2026-01-01", "amount": 1000, "type": "expense"}).json()
    t2 = client.post("/api/transactions", json={"accountId": acc["id"], "transactionDate": "2026-01-02", "amount": 2000, "type": "expense"}).json()

    res = client.post("/api/transactions/bulk-update", json={"ids": [t1["id"], t2["id"]], "categoryId": cat["id"]})
    assert res.status_code == 200
    assert res.json()["count"] == 2

    check = client.get(f"/api/transactions/{t1['id']}").json()
    assert check["category_id"] == cat["id"]


def test_description_parser_runs_on_manual_creation(client):
    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()
    txn = client.post("/api/transactions", json={
        "accountId": acc["id"], "transactionDate": "2026-01-01", "amount": 1000, "type": "expense",
        "description": "انتقال به آقای علی رضایی بانک ملت",
    }).json()
    check = client.get(f"/api/transactions/{txn['id']}").json()
    assert check["counterparty"] == "علی رضایی"
    assert check["bank_name"] == "ملت"


def test_every_displayed_column_field_can_be_edited_inline(client):
    """رگرسیون: هر فیلدی که در جدول Excel-like نمایش داده می‌شود باید از طریق PUT قابل ویرایش باشد."""
    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()
    txn = client.post("/api/transactions", json={
        "accountId": acc["id"], "transactionDate": "2026-01-01", "amount": 1000, "type": "expense",
    }).json()
    txn_id = txn["id"]

    client.put(f"/api/transactions/{txn_id}", json={"transactionDate": "2026-02-15"})
    client.put(f"/api/transactions/{txn_id}", json={"amount": 55000})
    client.put(f"/api/transactions/{txn_id}", json={"rawTransactionType": "خرید حضوری"})
    client.put(f"/api/transactions/{txn_id}", json={"counterparty": "رضا کریمی"})
    client.put(f"/api/transactions/{txn_id}", json={"cardNumber": "6274123456781234"})
    client.put(f"/api/transactions/{txn_id}", json={"bankName": "سامان"})

    check = client.get(f"/api/transactions/{txn_id}").json()
    assert check["transaction_date"] == "2026-02-15"
    assert check["amount"] == 55000
    assert check["raw_transaction_type"] == "خرید حضوری"
    assert check["counterparty"] == "رضا کریمی"
    assert check["card_number"] == "6274123456781234"
    assert check["bank_name"] == "سامان"


def test_error_response_shape_matches_frontend_expectation(client):
    """
    رگرسیون مهم: فرانت‌اند React (بدون تغییر) انتظار {"error": ...} دارد، نه فرمت پیش‌فرض
    FastAPI که {"detail": ...} است. بدون exception handler سفارشی در app/main.py، این تست fail می‌شد.
    """
    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()
    cat = client.post("/api/categories", json={"name": "خوراک"}).json()
    client.post("/api/transactions", json={"accountId": acc["id"], "transactionDate": "2026-01-01", "amount": 1000, "type": "expense", "categoryId": cat["id"]})
    res = client.delete(f"/api/categories/{cat['id']}")
    assert res.status_code == 400
    assert "error" in res.json()
    assert "detail" not in res.json()


def test_transfer_moves_real_money(client):
    a = client.post("/api/accounts", json={"name": "A", "type": "bank", "initialBalance": 1000000}).json()
    b = client.post("/api/accounts", json={"name": "B", "type": "bank", "initialBalance": 0}).json()
    client.post("/api/transfers", json={"fromAccountId": a["id"], "toAccountId": b["id"], "amount": 300000, "date": "2026-01-05"})

    accounts = {acc["id"]: acc for acc in client.get("/api/accounts").json()}
    assert accounts[a["id"]]["balance"] == 700000
    assert accounts[b["id"]]["balance"] == 300000


def test_no_trailing_slash_redirect_on_collection_routes(client):
    """
    رگرسیون واقعی: FastAPI/Starlette به‌طور پیش‌فرض از "/api/accounts" به "/api/accounts/"
    ریدایرکت می‌کند اگر route با "/" (نه "") ثبت شده باشد. TestClient این را به‌طور پیش‌فرض دنبال
    می‌کند و باگ را مخفی می‌کرد؛ فقط با یک کلاینت واقعی (مثل curl بدون -L) در تست زنده HTTP پیدا شد.
    فرانت‌اند بدون trailing slash درخواست می‌دهد، پس این رفتار باید مستقیماً 200 بدهد نه 307.
    """
    res = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}, follow_redirects=False)
    assert res.status_code != 307
    assert res.status_code == 201

    res2 = client.get("/api/accounts", follow_redirects=False)
    assert res2.status_code != 307
    assert res2.status_code == 200


def test_bulk_exclude_removes_transaction_from_dashboard_totals(client):
    """
    سناریوی واقعی کاربر: واریز بین کارت‌های خودش. بعد از bulk-exclude، موجودی حساب باید درست
    بماند ولی این تراکنش در آمار درآمد/هزینه ماه لحاظ نشود.
    """
    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()
    from datetime import date
    today = date.today().isoformat()
    txn = client.post("/api/transactions", json={
        "accountId": acc["id"], "transactionDate": today, "amount": 500000, "type": "income",
        "description": "واریز از کارت خودم",
    }).json()

    before = client.get("/api/dashboard/summary").json()
    assert before["currentMonth"]["income"] == 500000

    res = client.post("/api/transactions/bulk-exclude", json={"ids": [txn["id"]], "excluded": True})
    assert res.status_code == 200
    assert res.json()["count"] == 1

    after = client.get("/api/dashboard/summary").json()
    assert after["currentMonth"]["income"] == 0  # دیگر در آنالیز حساب نمی‌شود

    accounts = {a["id"]: a for a in client.get("/api/accounts").json()}
    assert accounts[acc["id"]]["balance"] == 500000  # ولی موجودی حساب همچنان درست است


def test_rule_with_raw_transaction_type_field_and_multi_tag_action(client):
    """
    رگرسیون: قبلاً Zod/Pydantic روی condition.field فقط چهار مقدار قدیمی را قبول می‌کرد،
    'rawTransactionType' رد می‌شد با خطای اعتبارسنجی. این تست هم ساخت قانون با این فیلد را
    تأیید می‌کند، هم این‌که یک تراکنش می‌تواند چند تگ از یک قانون بگیرد، هم این‌که
    run-on-uncategorized حالا روی تراکنش‌های «بدون تگ» هم اجرا می‌شود نه فقط «بدون دسته‌بندی».
    """
    cat = client.post("/api/categories", json={"name": "قبوض تست"}).json()
    tag1 = client.post("/api/tags", json={"name": "ماهانه"}).json()
    tag2 = client.post("/api/tags", json={"name": "ثابت"}).json()

    rule_res = client.post("/api/rules", json={
        "name": "قبض آب",
        "condition": {"field": "rawTransactionType", "op": "equals", "value": "قبض آب مصرفی"},
        "actions": {"categoryId": cat["id"], "tagIds": [tag1["id"], tag2["id"]]},
        "active": True,
        "autoApply": True,
    })
    assert rule_res.status_code == 201

    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()
    txn = client.post("/api/transactions", json={
        "accountId": acc["id"], "transactionDate": "2026-01-01", "amount": 50000, "type": "expense",
    }).json()
    # این تراکنش عمداً دسته‌بندی دارد ولی تگ ندارد — باید همچنان توسط run-on-uncategorized بررسی شود
    client.put(f"/api/transactions/{txn['id']}", json={"categoryId": cat["id"], "rawTransactionType": "قبض آب مصرفی"})

    run_res = client.post("/api/rules/run-on-uncategorized")
    assert run_res.status_code == 200
    assert run_res.json()["applied"], "قانون باید روی تراکنش دسته‌بندی‌شده-ولی-بدون‌تگ اعمال شود"

    check = client.get(f"/api/transactions/{txn['id']}").json()
    tag_names = {t["name"] for t in check["tags"]}
    assert tag_names == {"ماهانه", "ثابت"}


def test_yearly_report_scopes_to_jalali_calendar_year(client):
    """
    رگرسیون کلیدی: بازه باید دقیقاً یک سال شمسی کامل باشد (نه سال میلادی)، و تراکنش خارج از
    این بازه نباید در گزارش لحاظ شود. همچنین روند ماهانه باید بر اساس ماه شمسی گروه‌بندی شود.
    """
    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()
    cat = client.post("/api/categories", json={"name": "خوراک تست"}).json()
    tag = client.post("/api/tags", json={"name": "مهم"}).json()

    t1 = client.post("/api/transactions", json={
        "accountId": acc["id"], "transactionDate": "2025-05-01", "amount": 100000, "type": "expense", "categoryId": cat["id"],
    }).json()
    client.post("/api/transactions", json={
        "accountId": acc["id"], "transactionDate": "2025-08-15", "amount": 200000, "type": "expense", "categoryId": cat["id"],
    })
    client.put(f"/api/transactions/{t1['id']}", json={"tagIds": [tag["id"]]})
    # خارج از سال شمسی ۱۴۰۴ — نباید در گزارش بیاید
    client.post("/api/transactions", json={
        "accountId": acc["id"], "transactionDate": "2024-01-01", "amount": 999999, "type": "expense", "categoryId": cat["id"],
    })

    res = client.get("/api/dashboard/yearly?year=1404")
    assert res.status_code == 200
    body = res.json()
    assert body["totalExpense"] == 300000
    assert body["from"] == "2025-03-21"
    assert [m["month"] for m in body["monthlyTrend"]] == ["1404/02", "1404/05"]
    assert body["byCategory"][0]["categoryName"] == "خوراک تست"
    assert body["byCategory"][0]["total"] == 300000
    assert body["byTag"][0]["tagName"] == "مهم"
    assert body["byTag"][0]["total"] == 100000


def test_by_tag_report_lets_one_transaction_count_toward_multiple_tags(client):
    """برخلاف دسته‌بندی (یک‌به‌یک)، یک تراکنش می‌تواند در چند ردیف گزارش برچسب ظاهر شود."""
    acc = client.post("/api/accounts", json={"name": "حساب", "type": "bank", "initialBalance": 0}).json()
    tag1 = client.post("/api/tags", json={"name": "سفر"}).json()
    tag2 = client.post("/api/tags", json={"name": "کاری"}).json()
    txn = client.post("/api/transactions", json={
        "accountId": acc["id"], "transactionDate": "2026-01-01", "amount": 500000, "type": "expense",
    }).json()
    client.put(f"/api/transactions/{txn['id']}", json={"tagIds": [tag1["id"], tag2["id"]]})

    res = client.get("/api/dashboard/by-tag?from=2026-01-01&to=2026-01-31&type=expense")
    assert res.status_code == 200
    totals = {row["tagName"]: row["total"] for row in res.json()}
    assert totals == {"سفر": 500000, "کاری": 500000}


def test_import_workflow_end_to_end(client):
    from pathlib import Path
    fixture = Path(__file__).parent / "fixtures" / "openpyxl-sample.xlsx"
    acc = client.post("/api/accounts", json={"name": "حساب بانک", "type": "bank", "initialBalance": 0}).json()

    with open(fixture, "rb") as f:
        res = client.post("/api/transactions/import/commit", files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, data={"accountId": acc["id"]})
    assert res.status_code == 201
    assert res.json()["new_count"] == 3

    # reimport should be all duplicates now
    with open(fixture, "rb") as f:
        res2 = client.post("/api/transactions/import/commit", files={"file": ("test.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}, data={"accountId": acc["id"]})
    assert res2.json()["definite_duplicate_count"] >= 2
