import pytest
from app.db import open_db
from app.lib.balance import calculate_account_balance, calculate_period_totals
from app.lib.transfer import create_transfer


@pytest.fixture
def conn():
    c = open_db(":memory:")
    yield c
    c.close()


def test_initial_balance_no_transactions(conn):
    cur = conn.execute("INSERT INTO accounts (name, type, initial_balance) VALUES ('حساب اصلی','bank',1000000)")
    conn.commit()
    assert calculate_account_balance(conn, cur.lastrowid) == 1000000


def test_income_increases_expense_decreases(conn):
    cur = conn.execute("INSERT INTO accounts (name, type, initial_balance) VALUES ('حساب','bank',0)")
    conn.commit()
    account_id = cur.lastrowid
    conn.execute("INSERT INTO transactions (account_id, transaction_date, amount, type) VALUES (?, '2026-01-01', 500000, 'income')", (account_id,))
    conn.execute("INSERT INTO transactions (account_id, transaction_date, amount, type) VALUES (?, '2026-01-02', 200000, 'expense')", (account_id,))
    conn.commit()
    assert calculate_account_balance(conn, account_id) == 300000


def test_transfer_moves_money_correctly(conn):
    a = conn.execute("INSERT INTO accounts (name, type, initial_balance) VALUES ('A','bank',1000000)").lastrowid
    b = conn.execute("INSERT INTO accounts (name, type, initial_balance) VALUES ('B','bank',0)").lastrowid
    conn.commit()
    create_transfer(conn, a, b, 300000, "2026-01-05")
    assert calculate_account_balance(conn, a) == 700000
    assert calculate_account_balance(conn, b) == 300000


def test_transfer_not_counted_as_income_or_expense(conn):
    a = conn.execute("INSERT INTO accounts (name, type, initial_balance) VALUES ('A','bank',1000000)").lastrowid
    b = conn.execute("INSERT INTO accounts (name, type, initial_balance) VALUES ('B','bank',0)").lastrowid
    conn.commit()
    create_transfer(conn, a, b, 300000, "2026-01-05")
    totals = calculate_period_totals(conn, "2026-01-01", "2026-01-31", account_id=a)
    assert totals["income"] == 0
    assert totals["expense"] == 0


def test_no_float_drift_with_integer_amounts(conn):
    cur = conn.execute("INSERT INTO accounts (name, type, initial_balance) VALUES ('حساب','bank',0)")
    conn.commit()
    account_id = cur.lastrowid
    for _ in range(100):
        conn.execute("INSERT INTO transactions (account_id, transaction_date, amount, type) VALUES (?, '2026-01-01', 333, 'income')", (account_id,))
    conn.commit()
    balance = calculate_account_balance(conn, account_id)
    assert balance == 33300
    assert isinstance(balance, int)


def test_excluded_transactions_still_count_toward_account_balance(conn):
    """پول واقعاً جابه‌جا شده، پس موجودی حساب باید درست بماند حتی اگر از آنالیز استثنا شده باشد."""
    cur = conn.execute("INSERT INTO accounts (name, type, initial_balance) VALUES ('حساب','bank',1000000)")
    conn.commit()
    account_id = cur.lastrowid
    conn.execute(
        "INSERT INTO transactions (account_id, transaction_date, amount, type, excluded_from_analysis) VALUES (?, '2026-01-01', 200000, 'expense', 1)",
        (account_id,),
    )
    conn.commit()
    assert calculate_account_balance(conn, account_id) == 800000


def test_excluded_transactions_are_left_out_of_period_totals(conn):
    """مثال کاربر: واریز بین کارت‌های خودش یا به «باکس» نباید در آنالیز درآمد/هزینه حساب شود."""
    cur = conn.execute("INSERT INTO accounts (name, type, initial_balance) VALUES ('حساب','bank',0)")
    conn.commit()
    account_id = cur.lastrowid
    conn.execute("INSERT INTO transactions (account_id, transaction_date, amount, type) VALUES (?, '2026-01-01', 500000, 'income')", (account_id,))
    conn.execute(
        "INSERT INTO transactions (account_id, transaction_date, amount, type, excluded_from_analysis) VALUES (?, '2026-01-02', 300000, 'income', 1)",
        (account_id,),
    )
    conn.commit()
    totals = calculate_period_totals(conn, "2026-01-01", "2026-01-31", account_id=account_id)
    assert totals["income"] == 500000  # فقط تراکنش غیر-excluded
