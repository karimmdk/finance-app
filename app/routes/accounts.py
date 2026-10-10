import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_db
from app.schemas import AccountIn, AccountUpdate
from app.lib.balance import calculate_account_balance

router = APIRouter()


@router.get("")
def list_accounts(db: sqlite3.Connection = Depends(get_db)):
    accounts = [dict(r) for r in db.execute("SELECT * FROM accounts ORDER BY name")]
    for a in accounts:
        a["balance"] = calculate_account_balance(db, a["id"])
    return accounts


@router.get("/{account_id}")
def get_account(account_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not row:
        raise HTTPException(404, "حساب یافت نشد")
    account = dict(row)
    account["balance"] = calculate_account_balance(db, account_id)
    return account


@router.post("", status_code=201)
def create_account(body: AccountIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        """INSERT INTO accounts (name, type, bank_name, account_number, card_number, iban, initial_balance, currency, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (body.name, body.type, body.bankName, body.accountNumber, body.cardNumber, body.iban,
         body.initialBalance, body.currency, body.notes),
    )
    db.commit()
    return {"id": cur.lastrowid}


@router.put("/{account_id}")
def update_account(account_id: int, body: AccountUpdate, db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "حساب یافت نشد")
    merged = dict(existing)
    col_map = {"bankName": "bank_name", "accountNumber": "account_number", "cardNumber": "card_number",
               "initialBalance": "initial_balance"}
    for field, value in body.model_dump(exclude_unset=True).items():
        merged[col_map.get(field, field)] = value
    if not merged["name"]:
        raise HTTPException(400, "نام حساب الزامی است")
    db.execute(
        "UPDATE accounts SET name=?, type=?, bank_name=?, account_number=?, card_number=?, iban=?, "
        "initial_balance=?, currency=?, notes=?, active=?, updated_at=datetime('now') WHERE id=?",
        (merged["name"], merged["type"], merged["bank_name"], merged["account_number"], merged["card_number"],
         merged["iban"], merged["initial_balance"], merged["currency"], merged["notes"], merged["active"], account_id),
    )
    db.commit()
    return {"ok": True}


@router.delete("/{account_id}")
def delete_account(account_id: int, db: sqlite3.Connection = Depends(get_db)):
    in_use = db.execute("SELECT COUNT(*) as c FROM transactions WHERE account_id = ?", (account_id,)).fetchone()["c"]
    if in_use > 0:
        raise HTTPException(400, "این حساب دارای تراکنش است — به‌جای حذف، غیرفعال کنید")
    db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    db.commit()
    return {"ok": True}
