"""محاسبات فروش قسطی — معادل src/lib/installment-sale.ts."""
import sqlite3


def create_installment_sale(conn: sqlite3.Connection, customer_id: int, date: str, item_amount: int,
                             discount: int = 0, down_payment: int = 0, installment_count: int = 1,
                             payment_terms: str | None = None) -> int:
    final_amount = item_amount - discount
    cur = conn.execute(
        "INSERT INTO installment_sales (customer_id, date, item_amount, discount, final_amount, down_payment, installment_count, payment_terms) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (customer_id, date, item_amount, discount, final_amount, down_payment, installment_count, payment_terms),
    )
    conn.commit()
    return cur.lastrowid


def get_sale_balance(conn: sqlite3.Connection, sale_id: int) -> dict:
    """مانده فروش قسطی = final_amount - down_payment - Σ sale_payments."""
    sale = conn.execute("SELECT final_amount, down_payment FROM installment_sales WHERE id = ?", (sale_id,)).fetchone()
    if sale is None:
        raise ValueError(f"Sale {sale_id} not found")
    paid_row = conn.execute("SELECT COALESCE(SUM(amount), 0) AS paid FROM sale_payments WHERE sale_id = ?", (sale_id,)).fetchone()
    remaining = sale["final_amount"] - sale["down_payment"] - paid_row["paid"]
    return {"final_amount": sale["final_amount"], "down_payment": sale["down_payment"], "paid": paid_row["paid"], "remaining": remaining}


def record_sale_payment(conn: sqlite3.Connection, sale_id: int, amount: int, date: str,
                         account_id: int | None = None, transaction_id: int | None = None, notes: str | None = None) -> None:
    conn.execute(
        "INSERT INTO sale_payments (sale_id, date, amount, account_id, transaction_id, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (sale_id, date, amount, account_id, transaction_id, notes),
    )
    conn.commit()
