import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_db
from app.schemas import TransferIn
from app.lib.transfer import create_transfer

router = APIRouter()


@router.get("")
def list_transfers(db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute(
        """SELECT transfer_id, MIN(id) as id, account_id, amount, transaction_date, description
           FROM transactions WHERE type = 'transfer' GROUP BY transfer_id ORDER BY transaction_date DESC"""
    )]


@router.post("", status_code=201)
def create_transfer_route(body: TransferIn, db: sqlite3.Connection = Depends(get_db)):
    if body.fromAccountId == body.toAccountId:
        raise HTTPException(400, "حساب مبدأ و مقصد نمی‌توانند یکسان باشند")
    return create_transfer(db, body.fromAccountId, body.toAccountId, body.amount, body.date, body.description)


@router.delete("/{transfer_id}")
def delete_transfer(transfer_id: str, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM transactions WHERE transfer_id = ?", (transfer_id,))
    db.commit()
    return {"ok": True}
