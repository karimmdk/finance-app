"""انتقال بین حساب‌ها — معادل src/lib/transfer.ts."""
import sqlite3
import uuid
from app.db import transaction as db_transaction


def create_transfer(conn: sqlite3.Connection, from_account_id: int, to_account_id: int, amount: int, date: str, description: str | None = None) -> dict:
    """
    دو رکورد transaction با یک transfer_id مشترک می‌سازد. amount مبدأ منفی (خروج) و مقصد
    مثبت (ورود) ذخیره می‌شود — balance.py این علامت را مستقیم جمع می‌زند.
    """
    transfer_id = str(uuid.uuid4())
    with db_transaction(conn):
        cur = conn.execute(
            "INSERT INTO transactions (account_id, transaction_date, amount, type, description, transfer_id, source) "
            "VALUES (?, ?, ?, 'transfer', ?, ?, 'manual')",
            (from_account_id, date, -abs(amount), description or f"انتقال به حساب {to_account_id}", transfer_id),
        )
        from_txn_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO transactions (account_id, transaction_date, amount, type, description, transfer_id, source) "
            "VALUES (?, ?, ?, 'transfer', ?, ?, 'manual')",
            (to_account_id, date, abs(amount), description or f"انتقال از حساب {from_account_id}", transfer_id),
        )
        to_txn_id = cur.lastrowid

    return {"transfer_id": transfer_id, "from_transaction_id": from_txn_id, "to_transaction_id": to_txn_id}
