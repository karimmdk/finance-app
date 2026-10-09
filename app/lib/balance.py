"""محاسبات موجودی حساب — معادل src/lib/balance.ts. کاملاً deterministic، هرگز AI اینجا وارد نمی‌شود."""
import sqlite3


def calculate_account_balance(conn: sqlite3.Connection, account_id: int) -> int:
    """
    موجودی فعلی یک حساب = initial_balance + Σ(income) - Σ(expense) + Σ(transfer امضادار) + Σ(adjustment امضادار)
    transfer و adjustment با علامت (مثبت=ورود، منفی=خروج) ذخیره می‌شوند و مستقیم جمع می‌شوند.
    """
    account = conn.execute("SELECT initial_balance FROM accounts WHERE id = ?", (account_id,)).fetchone()
    if account is None:
        raise ValueError(f"Account {account_id} not found")

    row = conn.execute(
        """SELECT
             COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) AS income,
             COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS expense,
             COALESCE(SUM(CASE WHEN type = 'transfer' THEN amount ELSE 0 END), 0) AS transfer_net,
             COALESCE(SUM(CASE WHEN type = 'adjustment' THEN amount ELSE 0 END), 0) AS adjustment_net
           FROM transactions WHERE account_id = ?""",
        (account_id,),
    ).fetchone()

    return account["initial_balance"] + row["income"] - row["expense"] + row["transfer_net"] + row["adjustment_net"]


def calculate_total_balance(conn: sqlite3.Connection) -> int:
    accounts = conn.execute("SELECT id FROM accounts WHERE active = 1").fetchall()
    return sum(calculate_account_balance(conn, a["id"]) for a in accounts)


def calculate_period_totals(conn: sqlite3.Connection, from_date: str, to_date: str, account_id: int | None = None) -> dict:
    """
    نکته: excluded_from_analysis اینجا اعمال می‌شود (نه در calculate_account_balance) — چون
    پول واقعاً جابه‌جا شده و باید در موجودی حساب باشد، ولی درآمد/هزینه واقعی محسوب نمی‌شود
    (مثل واریز بین کارت‌های خودِ کاربر یا «باکس»).
    """
    params: list = [from_date, to_date]
    sql = """SELECT
                COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) AS income,
                COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) AS expense
              FROM transactions WHERE transaction_date BETWEEN ? AND ? AND excluded_from_analysis = 0"""
    if account_id is not None:
        sql += " AND account_id = ?"
        params.append(account_id)
    row = conn.execute(sql, params).fetchone()
    return {"income": row["income"], "expense": row["expense"], "net": row["income"] - row["expense"]}
