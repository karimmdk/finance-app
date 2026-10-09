"""محاسبات بدهی/طلب — معادل src/lib/debt.ts."""
import sqlite3
from app.db import transaction as db_transaction


def create_debt(conn: sqlite3.Connection, kind: str, person_id: int, original_amount: int, created_date: str,
                 due_date: str | None = None, description: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO debts (kind, person_id, original_amount, paid_amount, created_date, due_date, description, status) "
        "VALUES (?, ?, ?, 0, ?, ?, ?, 'open')",
        (kind, person_id, original_amount, created_date, due_date, description),
    )
    conn.commit()
    return cur.lastrowid


def get_debt_balance(conn: sqlite3.Connection, debt_id: int) -> dict:
    """مانده بدهی/طلب = original_amount - Σ payments (همیشه محاسبه‌شده، هرگز cache قدیمی)."""
    debt = conn.execute("SELECT original_amount FROM debts WHERE id = ?", (debt_id,)).fetchone()
    if debt is None:
        raise ValueError(f"Debt {debt_id} not found")
    paid_row = conn.execute("SELECT COALESCE(SUM(amount), 0) AS paid FROM debt_payments WHERE debt_id = ?", (debt_id,)).fetchone()
    return {"original": debt["original_amount"], "paid": paid_row["paid"], "remaining": debt["original_amount"] - paid_row["paid"]}


def record_debt_payment(conn: sqlite3.Connection, debt_id: int, amount: int, date: str, transaction_id: int | None = None) -> None:
    with db_transaction(conn):
        conn.execute(
            "INSERT INTO debt_payments (debt_id, transaction_id, amount, date) VALUES (?, ?, ?, ?)",
            (debt_id, transaction_id, amount, date),
        )
        remaining = get_debt_balance(conn, debt_id)["remaining"]
        status = "settled" if remaining <= 0 else "open"
        conn.execute("UPDATE debts SET status = ? WHERE id = ?", (status, debt_id))


def get_person_net_position(conn: sqlite3.Connection, person_id: int) -> dict:
    debts = conn.execute("SELECT id, kind FROM debts WHERE person_id = ?", (person_id,)).fetchall()
    receivable = payable = 0
    for d in debts:
        remaining = get_debt_balance(conn, d["id"])["remaining"]
        if d["kind"] == "receivable":
            receivable += remaining
        else:
            payable += remaining
    return {"receivable": receivable, "payable": payable, "net": receivable - payable}
