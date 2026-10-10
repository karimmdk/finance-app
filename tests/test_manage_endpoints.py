"""ویرایش/حذف بدهی-طلب، وام، فروش قسطی، مشتری، برچسب، بودجه، انتقال و حساب."""
import pytest
from fastapi.testclient import TestClient
from app.db import open_db
from app.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app(open_db(":memory:")))


def _account(c, name="حساب", balance=0):
    return c.post("/api/accounts", json={"name": name, "type": "bank", "initialBalance": balance}).json()


def _accounts(c):
    return {a["name"]: a for a in c.get("/api/accounts").json()}


def test_debt_edit_recomputes_status_and_payment_edit_delete(client):
    p1 = client.post("/api/people", json={"name": "علی"}).json()["id"]
    p2 = client.post("/api/people", json={"name": "رضا"}).json()["id"]
    d = client.post("/api/debts", json={"kind": "payable", "personId": p1, "originalAmount": 1000, "createdDate": "2026-01-01"}).json()["id"]
    client.post(f"/api/debts/{d}/payments", json={"amount": 1000, "date": "2026-01-02"})
    assert client.get(f"/api/debts/{d}").json()["status"] == "settled"

    # بالا بردن مبلغ → دوباره باز می‌شود؛ تغییر نوع و شخص؛ پاک کردن سررسید
    r = client.put(f"/api/debts/{d}", json={"originalAmount": 5000, "kind": "receivable", "personId": p2, "dueDate": ""})
    assert r.status_code == 200
    debt = client.get(f"/api/debts/{d}").json()
    assert (debt["status"], debt["kind"], debt["person_id"], debt["due_date"]) == ("open", "receivable", p2, None)
    assert debt["balance"]["remaining"] == 4000

    pay_id = debt["payments"][0]["id"]
    client.put(f"/api/debts/{d}/payments/{pay_id}", json={"amount": 5000})
    assert client.get(f"/api/debts/{d}").json()["status"] == "settled"
    assert client.delete(f"/api/debts/{d}/payments/{pay_id}").status_code == 200
    after = client.get(f"/api/debts/{d}").json()
    assert after["payments"] == [] and after["status"] == "open"

    assert client.put(f"/api/debts/{d}", json={"originalAmount": 0}).status_code == 400
    assert client.put("/api/debts/999", json={"originalAmount": 5}).status_code == 404
    assert client.delete(f"/api/debts/{d}/payments/12345").status_code == 404


def test_loan_edit_info_regenerates_schedule_only_without_payments(client):
    loan = client.post("/api/loans", json={"name": "وام", "lender": "بانک", "principal": 600, "termMonths": 6,
                                            "installmentAmount": 100, "startDate": "2026-01-01"}).json()["id"]
    # فقط اطلاعات متنی → جدول اقساط دست نمی‌خورد
    assert client.put(f"/api/loans/{loan}", json={"name": "وام جدید", "notes": "یادداشت"}).status_code == 200
    got = client.get(f"/api/loans/{loan}").json()
    assert got["name"] == "وام جدید" and len(got["installments"]) == 6

    # تغییر تعداد اقساط → جدول از نو ساخته می‌شود
    assert client.put(f"/api/loans/{loan}", json={"termMonths": 3, "installmentAmount": 200}).status_code == 200
    got = client.get(f"/api/loans/{loan}").json()
    assert len(got["installments"]) == 3 and sum(i["amount"] for i in got["installments"]) == 600

    # با پرداخت ثبت‌شده نمی‌شود جدول را عوض کرد؛ اول باید پرداخت صفر شود
    first = got["installments"][0]["id"]
    client.post(f"/api/loans/installments/{first}/payments", json={"amount": 200})
    assert client.put(f"/api/loans/{loan}", json={"termMonths": 4}).status_code == 400
    assert client.put(f"/api/loans/installments/{first}", json={"paidAmount": 0}).status_code == 200
    inst = client.get(f"/api/loans/{loan}").json()["installments"][0]
    assert inst["paid_amount"] == 0 and inst["status"] != "paid"
    assert client.put(f"/api/loans/{loan}", json={"termMonths": 4}).status_code == 200
    assert len(client.get(f"/api/loans/{loan}").json()["installments"]) == 4

    current = client.get(f"/api/loans/{loan}").json()["installments"][0]["id"]   # جدول از نو ساخته شده؛ شناسه‌ها عوض شده
    assert client.put(f"/api/loans/installments/{current}", json={"paidAmount": -5}).status_code == 400
    assert client.put(f"/api/loans/installments/{first}", json={"paidAmount": 1}).status_code == 404
    assert client.put("/api/loans/999", json={"name": "x"}).status_code == 404


def test_customer_and_sale_edit_delete_with_payments(client):
    c1 = client.post("/api/customers", json={"name": "الف"}).json()["id"]
    assert client.put(f"/api/customers/{c1}", json={"name": "ب", "phone": "0912"}).status_code == 200
    assert client.put("/api/customers/99", json={"name": "ب"}).status_code == 404

    s = client.post("/api/installment-sales", json={"customerId": c1, "date": "2026-02-01", "itemAmount": 1000,
                                                     "discount": 100, "downPayment": 200, "installmentCount": 4}).json()["id"]
    client.post(f"/api/installment-sales/{s}/payments", json={"amount": 300, "date": "2026-03-01"})
    assert client.put(f"/api/installment-sales/{s}", json={"discount": 200, "installmentCount": 5}).status_code == 200
    sale = client.get(f"/api/installment-sales/{s}").json()
    assert sale["final_amount"] == 800 and sale["installment_count"] == 5
    assert sale["balance"]["remaining"] == 800 - 200 - 300

    pid = sale["payments"][0]["id"]
    client.put(f"/api/installment-sales/{s}/payments/{pid}", json={"amount": 600})
    assert client.get(f"/api/installment-sales/{s}").json()["balance"]["remaining"] == 0
    client.delete(f"/api/installment-sales/{s}/payments/{pid}")
    assert client.get(f"/api/installment-sales/{s}").json()["payments"] == []

    assert client.put(f"/api/installment-sales/{s}", json={"discount": 5000}).status_code == 400
    assert client.delete(f"/api/installment-sales/{s}").status_code == 200
    assert client.get(f"/api/installment-sales/{s}").status_code == 404
    assert client.delete(f"/api/installment-sales/{s}").status_code == 404
    # حالا مشتری بدون فروش قابل حذف است
    assert client.delete(f"/api/customers/{c1}").status_code == 200


def test_tag_budget_transfer_and_full_account_edit(client):
    t = client.post("/api/tags", json={"name": "الف"}).json()["id"]
    client.post("/api/tags", json={"name": "ب"})
    assert client.put(f"/api/tags/{t}", json={"name": "ج", "color": "#fff"}).status_code == 200
    assert client.put(f"/api/tags/{t}", json={"name": "ب"}).status_code == 409
    assert client.put("/api/tags/999", json={"name": "x"}).status_code == 404

    cat = client.get("/api/categories").json()[0]["id"]
    client.post("/api/budgets", json={"categoryId": cat, "month": "2026-05", "amount": 100})
    bid = client.get("/api/budgets/2026-05").json()[0]["id"]
    item = client.get(f"/api/budgets/item/{bid}").json()
    assert (item["month"], item["amount"], item["category_id"]) == ("2026-05", 100, cat) and item["category_name"]
    assert client.put(f"/api/budgets/{bid}", json={"amount": 250}).status_code == 200
    assert client.get("/api/budgets/2026-05").json()[0]["amount"] == 250
    assert client.put(f"/api/budgets/{bid}", json={"amount": -1}).status_code == 400

    a1, a2, a3 = (_account(client, n, 1000) for n in ("الف", "ب", "ج"))
    tr = client.post("/api/transfers", json={"fromAccountId": a1["id"], "toAccountId": a2["id"], "amount": 100, "date": "2026-05-01"}).json()["transfer_id"]
    bal = lambda: {k: v["balance"] for k, v in _accounts(client).items()}
    assert bal() == {"الف": 900, "ب": 1100, "ج": 1000}
    got_tr = client.get(f"/api/transfers/{tr}").json()
    assert (got_tr["fromAccountId"], got_tr["toAccountId"], got_tr["amount"]) == (a1["id"], a2["id"], 100)
    assert client.put(f"/api/transfers/{tr}", json={"amount": 300, "toAccountId": a3["id"], "date": "2026-05-02"}).status_code == 200
    assert bal() == {"الف": 700, "ب": 1000, "ج": 1300}
    assert client.put(f"/api/transfers/{tr}", json={"toAccountId": a1["id"]}).status_code == 400
    assert client.put("/api/transfers/nope", json={"amount": 5}).status_code == 404

    # ویرایش کامل حساب (قبلاً فقط نام/نوع/بانک/یادداشت/فعال بود)
    assert client.put(f"/api/accounts/{a1['id']}", json={"name": "الف۲", "initialBalance": 5000, "iban": "IR12", "cardNumber": "6037"}).status_code == 200
    got = client.get(f"/api/accounts/{a1['id']}").json()
    assert (got["name"], got["initial_balance"], got["iban"], got["card_number"]) == ("الف۲", 5000, "IR12", "6037")
    assert client.put(f"/api/accounts/{a1['id']}", json={"notes": "x"}).status_code == 200   # رفتار قبلی دست‌نخورده
    assert client.get(f"/api/accounts/{a1['id']}").json()["initial_balance"] == 5000
