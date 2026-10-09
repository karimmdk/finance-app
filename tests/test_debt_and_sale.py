import pytest
from app.db import open_db
from app.lib.debt import create_debt, get_debt_balance, record_debt_payment, get_person_net_position
from app.lib.installment_sale import create_installment_sale, get_sale_balance, record_sale_payment


@pytest.fixture
def conn():
    c = open_db(":memory:")
    yield c
    c.close()


@pytest.fixture
def person_id(conn):
    cur = conn.execute("INSERT INTO people (name) VALUES ('رضا')")
    conn.commit()
    return cur.lastrowid


def test_debt_remaining_balance(conn, person_id):
    debt_id = create_debt(conn, "receivable", person_id, 1000000, "2026-01-01")
    record_debt_payment(conn, debt_id, 300000, "2026-02-01")
    assert get_debt_balance(conn, debt_id)["remaining"] == 700000


def test_debt_settled_when_fully_paid(conn, person_id):
    debt_id = create_debt(conn, "payable", person_id, 500000, "2026-01-01")
    record_debt_payment(conn, debt_id, 500000, "2026-02-01")
    row = conn.execute("SELECT status FROM debts WHERE id = ?", (debt_id,)).fetchone()
    assert row["status"] == "settled"


def test_person_net_position(conn, person_id):
    create_debt(conn, "receivable", person_id, 1000000, "2026-01-01")
    create_debt(conn, "payable", person_id, 400000, "2026-01-01")
    net = get_person_net_position(conn, person_id)
    assert net == {"receivable": 1000000, "payable": 400000, "net": 600000}


@pytest.fixture
def customer_id(conn):
    cur = conn.execute("INSERT INTO customers (name) VALUES ('مشتری تست')")
    conn.commit()
    return cur.lastrowid


def test_sale_final_amount(conn, customer_id):
    sale_id = create_installment_sale(conn, customer_id, "2026-01-01", 50000000, discount=2000000, installment_count=10)
    sale = conn.execute("SELECT final_amount FROM installment_sales WHERE id = ?", (sale_id,)).fetchone()
    assert sale["final_amount"] == 48000000


def test_sale_remaining_balance(conn, customer_id):
    sale_id = create_installment_sale(conn, customer_id, "2026-01-01", 50000000, down_payment=10000000, installment_count=10)
    record_sale_payment(conn, sale_id, 5000000, "2026-02-01")
    balance = get_sale_balance(conn, sale_id)
    assert balance["remaining"] == 50000000 - 10000000 - 5000000
