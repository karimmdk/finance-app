import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_db
from app.schemas import CustomerIn, InstallmentSaleIn, SalePaymentIn
from app.lib.installment_sale import create_installment_sale, get_sale_balance, record_sale_payment

customers_router = APIRouter()
sales_router = APIRouter()


@customers_router.get("")
def list_customers(db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute("SELECT * FROM customers ORDER BY name")]


@customers_router.post("", status_code=201)
def create_customer(body: CustomerIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute("INSERT INTO customers (name, phone, description) VALUES (?, ?, ?)", (body.name, body.phone, body.description))
    db.commit()
    return {"id": cur.lastrowid}


@customers_router.delete("/{customer_id}")
def delete_customer(customer_id: int, db: sqlite3.Connection = Depends(get_db)):
    sales_count = db.execute("SELECT COUNT(*) as c FROM installment_sales WHERE customer_id = ?", (customer_id,)).fetchone()["c"]
    if sales_count > 0:
        raise HTTPException(400, "این مشتری دارای فروش قسطی ثبت‌شده است")
    db.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
    db.commit()
    return {"ok": True}


@sales_router.get("")
def list_sales(db: sqlite3.Connection = Depends(get_db)):
    sales = [dict(r) for r in db.execute(
        "SELECT s.*, c.name as customer_name FROM installment_sales s JOIN customers c ON c.id = s.customer_id ORDER BY s.date DESC"
    )]
    for s in sales:
        s["balance"] = get_sale_balance(db, s["id"])
    return sales


@sales_router.get("/{sale_id}")
def get_sale(sale_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM installment_sales WHERE id = ?", (sale_id,)).fetchone()
    if not row:
        raise HTTPException(404, "یافت نشد")
    sale = dict(row)
    sale["balance"] = get_sale_balance(db, sale_id)
    sale["payments"] = [dict(r) for r in db.execute("SELECT * FROM sale_payments WHERE sale_id = ? ORDER BY date", (sale_id,))]
    return sale


@sales_router.post("", status_code=201)
def create_sale(body: InstallmentSaleIn, db: sqlite3.Connection = Depends(get_db)):
    sale_id = create_installment_sale(db, body.customerId, body.date, body.itemAmount, body.discount,
                                       body.downPayment, body.installmentCount, body.paymentTerms)
    return {"id": sale_id}


@sales_router.post("/{sale_id}/payments", status_code=201)
def add_sale_payment(sale_id: int, body: SalePaymentIn, db: sqlite3.Connection = Depends(get_db)):
    sale = db.execute("SELECT id FROM installment_sales WHERE id = ?", (sale_id,)).fetchone()
    if not sale:
        raise HTTPException(404, "فروش یافت نشد")
    record_sale_payment(db, sale_id, body.amount, body.date, body.accountId, body.transactionId, body.notes)
    return get_sale_balance(db, sale_id)
