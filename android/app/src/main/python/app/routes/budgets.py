import sqlite3
from fastapi import APIRouter, Depends
from app.deps import get_db
from app.schemas import BudgetIn

router = APIRouter()


@router.get("/{month}")
def get_budgets(month: str, db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute(
        """SELECT b.*, c.name as category_name,
                  COALESCE((SELECT SUM(amount) FROM transactions t WHERE t.category_id = b.category_id
                            AND strftime('%Y-%m', t.transaction_date) = b.month AND t.type = 'expense'), 0) as spent
           FROM budgets b JOIN categories c ON c.id = b.category_id WHERE b.month = ?""",
        (month,),
    )]


@router.post("", status_code=201)
def upsert_budget(body: BudgetIn, db: sqlite3.Connection = Depends(get_db)):
    db.execute(
        """INSERT INTO budgets (category_id, month, amount) VALUES (?, ?, ?)
           ON CONFLICT(category_id, month) DO UPDATE SET amount = excluded.amount""",
        (body.categoryId, body.month, body.amount),
    )
    db.commit()
    return {"ok": True}


@router.delete("/{budget_id}")
def delete_budget(budget_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM budgets WHERE id = ?", (budget_id,))
    db.commit()
    return {"ok": True}
