import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_db
from app.schemas import DebtIn, DebtPaymentIn
from app.lib.debt import create_debt, get_debt_balance, record_debt_payment

router = APIRouter()


@router.get("")
def list_debts(kind: str | None = None, personId: int | None = None, status: str | None = None,
               db: sqlite3.Connection = Depends(get_db)):
    clauses, params = [], []
    if kind: clauses.append("kind = ?"); params.append(kind)
    if personId: clauses.append("person_id = ?"); params.append(personId)
    if status: clauses.append("status = ?"); params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = [dict(r) for r in db.execute(f"SELECT * FROM debts {where} ORDER BY due_date IS NULL, due_date", params)]
    for d in rows:
        d["balance"] = get_debt_balance(db, d["id"])
    return rows


@router.get("/{debt_id}")
def get_debt(debt_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM debts WHERE id = ?", (debt_id,)).fetchone()
    if not row:
        raise HTTPException(404, "یافت نشد")
    debt = dict(row)
    debt["balance"] = get_debt_balance(db, debt_id)
    debt["payments"] = [dict(r) for r in db.execute("SELECT * FROM debt_payments WHERE debt_id = ? ORDER BY date", (debt_id,))]
    return debt


@router.post("", status_code=201)
def create_debt_route(body: DebtIn, db: sqlite3.Connection = Depends(get_db)):
    debt_id = create_debt(db, body.kind, body.personId, body.originalAmount, body.createdDate, body.dueDate, body.description)
    return {"id": debt_id}


@router.post("/{debt_id}/payments", status_code=201)
def add_debt_payment(debt_id: int, body: DebtPaymentIn, db: sqlite3.Connection = Depends(get_db)):
    debt = db.execute("SELECT id FROM debts WHERE id = ?", (debt_id,)).fetchone()
    if not debt:
        raise HTTPException(404, "بدهی/طلب یافت نشد")
    record_debt_payment(db, debt_id, body.amount, body.date, body.transactionId)
    return get_debt_balance(db, debt_id)


@router.delete("/{debt_id}")
def delete_debt(debt_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM debt_payments WHERE debt_id = ?", (debt_id,))
    db.execute("DELETE FROM debts WHERE id = ?", (debt_id,))
    db.commit()
    return {"ok": True}
