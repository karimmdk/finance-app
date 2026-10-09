import sqlite3
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_db
from app.schemas import LoanIn, InstallmentPaymentIn
from app.lib.loan import create_loan_with_schedule, record_installment_payment, get_upcoming_installments, compute_installment_status
from app.lib.jalali import iso_to_jalali

router = APIRouter()


def _today_iso() -> str:
    return date.today().isoformat()


def _refresh_overdue_statuses(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT id, amount, paid_amount, due_date, status FROM installments WHERE status != 'paid'").fetchall()
    today = _today_iso()
    for r in rows:
        status = compute_installment_status(r["amount"], r["paid_amount"], r["due_date"], today)
        if status != r["status"]:
            db.execute("UPDATE installments SET status = ? WHERE id = ?", (status, r["id"]))
    db.commit()


@router.get("")
def list_loans(db: sqlite3.Connection = Depends(get_db)):
    _refresh_overdue_statuses(db)
    loans = [dict(r) for r in db.execute("SELECT * FROM loans ORDER BY start_date DESC")]
    for loan in loans:
        totals = db.execute(
            "SELECT COUNT(*) as total, SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) as paidCount, "
            "SUM(paid_amount) as paidAmount, SUM(amount) as totalAmount FROM installments WHERE loan_id = ?",
            (loan["id"],),
        ).fetchone()
        loan["progress"] = dict(totals)
    return loans


@router.get("/{loan_id}")
def get_loan(loan_id: int, db: sqlite3.Connection = Depends(get_db)):
    _refresh_overdue_statuses(db)
    row = db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone()
    if not row:
        raise HTTPException(404, "وام یافت نشد")
    loan = dict(row)
    installments = [dict(r) for r in db.execute("SELECT * FROM installments WHERE loan_id = ? ORDER BY installment_number", (loan_id,))]
    for i in installments:
        i["due_date_jalali"] = iso_to_jalali(i["due_date"])
    loan["installments"] = installments
    return loan


@router.post("", status_code=201)
def create_loan(body: LoanIn, db: sqlite3.Connection = Depends(get_db)):
    loan_id = create_loan_with_schedule(db, body.name, body.lender, body.principal, body.termMonths,
                                         body.installmentAmount, body.startDate, body.interestRateBps,
                                         body.accountId, body.notes)
    return {"id": loan_id}


@router.post("/installments/{installment_id}/payments")
def pay_installment(installment_id: int, body: InstallmentPaymentIn, db: sqlite3.Connection = Depends(get_db)):
    try:
        record_installment_payment(db, installment_id, body.amount, _today_iso(), body.transactionId)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/upcoming/{days}")
def upcoming_installments(days: int, db: sqlite3.Connection = Depends(get_db)):
    _refresh_overdue_statuses(db)
    return get_upcoming_installments(db, days, _today_iso())


@router.delete("/{loan_id}")
def delete_loan(loan_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM installments WHERE loan_id = ?", (loan_id,))
    db.execute("DELETE FROM loans WHERE id = ?", (loan_id,))
    db.commit()
    return {"ok": True}
