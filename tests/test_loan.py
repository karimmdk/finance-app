import pytest
from app.db import open_db
from app.lib.loan import (
    generate_installment_schedule, create_loan_with_schedule,
    compute_installment_status, record_installment_payment,
)


@pytest.fixture
def conn():
    c = open_db(":memory:")
    yield c
    c.close()


def test_schedule_sums_exactly():
    schedule = generate_installment_schedule(1, 100000000, 12, 8333333, "2026-01-01")
    assert sum(s["amount"] for s in schedule) == 8333333 * 12
    assert len(schedule) == 12
    assert schedule[0]["due_date"] == "2026-02-01"


def test_create_loan_with_persisted_schedule(conn):
    loan_id = create_loan_with_schedule(conn, "وام خودرو", "بانک سامان", 50000000, 6, 8500000, "2026-03-01")
    rows = conn.execute("SELECT * FROM installments WHERE loan_id = ?", (loan_id,)).fetchall()
    assert len(rows) == 6
    assert sum(r["amount"] for r in rows) == 8500000 * 6


def test_installment_status_cases():
    assert compute_installment_status(1000, 1000, "2026-01-01", "2026-02-01") == "paid"
    assert compute_installment_status(1000, 500, "2026-01-01", "2026-02-01") == "partially_paid"
    assert compute_installment_status(1000, 0, "2026-01-01", "2026-02-01") == "overdue"
    assert compute_installment_status(1000, 0, "2026-02-01", "2026-02-01") == "due"
    assert compute_installment_status(1000, 0, "2026-03-01", "2026-02-01") == "upcoming"


def test_record_installment_payment_updates_status(conn):
    loan_id = create_loan_with_schedule(conn, "وام", "بانک", 10000000, 2, 5000000, "2026-01-01")
    installment = conn.execute(
        "SELECT id FROM installments WHERE loan_id = ? ORDER BY installment_number LIMIT 1", (loan_id,)
    ).fetchone()
    record_installment_payment(conn, installment["id"], 5000000, "2026-03-01")
    updated = conn.execute("SELECT * FROM installments WHERE id = ?", (installment["id"],)).fetchone()
    assert updated["paid_amount"] == 5000000
    assert updated["status"] == "paid"
