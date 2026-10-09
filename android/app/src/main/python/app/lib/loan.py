"""محاسبات وام و اقساط — معادل src/lib/loan.ts."""
import sqlite3
from datetime import date as date_cls, timedelta
from app.db import transaction as db_transaction
from app.lib.jalali import iso_to_jalali


def _add_months(iso_date: str, months: int) -> str:
    y, m, d = (int(p) for p in iso_date.split("-"))
    total_months = (m - 1) + months
    new_y = y + total_months // 12
    new_m = total_months % 12 + 1
    # مطابق‌سازی روز با آخرین روز معتبر ماه مقصد (همان رفتار Date.setUTCMonth در JS)
    day = d
    while True:
        try:
            return date_cls(new_y, new_m, day).isoformat()
        except ValueError:
            day -= 1


def generate_installment_schedule(loan_id: int, principal: int, term_months: int, installment_amount: int, start_date: str) -> list[dict]:
    """
    ایجاد Schedule اقساط. مبلغ آخرین قسط با باقیمانده تنظیم می‌شود تا Σ اقساط دقیقاً برابر
    installment_amount * term_months باشد — بدون خطای رُند اعشاری (همه integer).
    """
    total_payable = installment_amount * term_months
    schedule = []
    remaining = total_payable
    for i in range(1, term_months + 1):
        is_last = i == term_months
        amount = remaining if is_last else installment_amount
        remaining -= amount
        schedule.append({
            "loan_id": loan_id,
            "installment_number": i,
            "due_date": _add_months(start_date, i),
            "amount": amount,
        })
    return schedule


def create_loan_with_schedule(conn: sqlite3.Connection, name: str, lender: str, principal: int, term_months: int,
                               installment_amount: int, start_date: str, interest_rate_bps: int | None = None,
                               account_id: int | None = None, notes: str | None = None) -> int:
    with db_transaction(conn):
        cur = conn.execute(
            "INSERT INTO loans (name, lender, principal, interest_rate, term_months, installment_amount, start_date, account_id, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (name, lender, principal, interest_rate_bps, term_months, installment_amount, start_date, account_id, notes),
        )
        loan_id = cur.lastrowid
        schedule = generate_installment_schedule(loan_id, principal, term_months, installment_amount, start_date)
        for inst in schedule:
            conn.execute(
                "INSERT INTO installments (loan_id, installment_number, due_date, amount, status) VALUES (?, ?, ?, ?, 'upcoming')",
                (inst["loan_id"], inst["installment_number"], inst["due_date"], inst["amount"]),
            )
    return loan_id


def compute_installment_status(amount: int, paid_amount: int, due_date_iso: str, today_iso: str) -> str:
    if paid_amount >= amount:
        return "paid"
    if paid_amount > 0:
        return "partially_paid"
    if due_date_iso < today_iso:
        return "overdue"
    if due_date_iso == today_iso:
        return "due"
    return "upcoming"


def record_installment_payment(conn: sqlite3.Connection, installment_id: int, amount: int, today_iso: str, transaction_id: int | None = None) -> None:
    with db_transaction(conn):
        inst = conn.execute("SELECT * FROM installments WHERE id = ?", (installment_id,)).fetchone()
        if inst is None:
            raise ValueError(f"Installment {installment_id} not found")
        new_paid = inst["paid_amount"] + amount
        status = compute_installment_status(inst["amount"], new_paid, inst["due_date"], today_iso)
        conn.execute(
            "UPDATE installments SET paid_amount = ?, status = ?, transaction_id = COALESCE(?, transaction_id) WHERE id = ?",
            (new_paid, status, transaction_id, installment_id),
        )


def get_upcoming_installments(conn: sqlite3.Connection, within_days: int, today_iso: str) -> list[dict]:
    y, m, d = (int(p) for p in today_iso.split("-"))
    future_iso = (date_cls(y, m, d) + timedelta(days=within_days)).isoformat()
    rows = conn.execute(
        """SELECT i.*, l.name as loan_name FROM installments i
           JOIN loans l ON l.id = i.loan_id
           WHERE i.due_date BETWEEN ? AND ? AND i.status != 'paid'
           ORDER BY i.due_date ASC""",
        (today_iso, future_iso),
    ).fetchall()
    result = []
    for r in rows:
        row = dict(r)
        row["due_date_jalali"] = iso_to_jalali(row["due_date"])
        result.append(row)
    return result
