"""
ویرایش و حذف موارد بیشتر: بدهی/طلب (و پرداخت‌هایش)، وام و اقساط، فروش قسطی (و پرداخت‌هایش)،
مشتری، برچسب، بودجه و انتقال بین حساب‌ها. فقط مسیرهای جدید اضافه شده؛ رفتار مسیرهای قبلی تغییری نکرده.
"""
import sqlite3
from datetime import date
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.db import transaction as db_transaction
from app.deps import get_db
from app.lib.loan import generate_installment_schedule, compute_installment_status
from app.schemas import CustomerIn, TagIn

router = APIRouter()


def _or_404(row, message: str):
    if row is None:
        raise HTTPException(404, message)
    return row


def _clean(value):
    """رشته خالی = پاک کردن مقدار (NULL)."""
    return None if value == "" else value


# ----------------------------------------------------------------- بدهی / طلب

class DebtUpdate(BaseModel):
    kind: Optional[Literal["receivable", "payable"]] = None
    personId: Optional[int] = None
    originalAmount: Optional[int] = None
    createdDate: Optional[str] = None
    dueDate: Optional[str] = None
    description: Optional[str] = None


class PaymentUpdate(BaseModel):
    amount: Optional[int] = None
    date: Optional[str] = None
    notes: Optional[str] = None


def _sync_debt_status(db: sqlite3.Connection, debt_id: int) -> None:
    row = db.execute("SELECT original_amount FROM debts WHERE id = ?", (debt_id,)).fetchone()
    paid = db.execute("SELECT COALESCE(SUM(amount), 0) AS p FROM debt_payments WHERE debt_id = ?", (debt_id,)).fetchone()["p"]
    status = "settled" if row["original_amount"] - paid <= 0 else "open"
    db.execute("UPDATE debts SET status = ? WHERE id = ?", (status, debt_id))


@router.put("/debts/{debt_id}")
def update_debt(debt_id: int, body: DebtUpdate, db: sqlite3.Connection = Depends(get_db)):
    existing = dict(_or_404(db.execute("SELECT * FROM debts WHERE id = ?", (debt_id,)).fetchone(), "بدهی/طلب یافت نشد"))
    changes = body.model_dump(exclude_unset=True)
    if "originalAmount" in changes and (changes["originalAmount"] is None or changes["originalAmount"] <= 0):
        raise HTTPException(400, "مبلغ باید عددی مثبت باشد")
    if "personId" in changes:
        _or_404(db.execute("SELECT id FROM people WHERE id = ?", (changes["personId"],)).fetchone(), "شخص یافت نشد")
    col = {"personId": "person_id", "originalAmount": "original_amount", "createdDate": "created_date", "dueDate": "due_date"}
    for field, value in changes.items():
        existing[col.get(field, field)] = _clean(value)
    with db_transaction(db):
        db.execute(
            "UPDATE debts SET kind=?, person_id=?, original_amount=?, created_date=?, due_date=?, description=? WHERE id=?",
            (existing["kind"], existing["person_id"], existing["original_amount"], existing["created_date"],
             existing["due_date"], existing["description"], debt_id),
        )
        _sync_debt_status(db, debt_id)
    return {"ok": True}


@router.put("/debts/{debt_id}/payments/{payment_id}")
def update_debt_payment(debt_id: int, payment_id: int, body: PaymentUpdate, db: sqlite3.Connection = Depends(get_db)):
    row = dict(_or_404(db.execute("SELECT * FROM debt_payments WHERE id = ? AND debt_id = ?", (payment_id, debt_id)).fetchone(), "پرداخت یافت نشد"))
    changes = body.model_dump(exclude_unset=True)
    if "amount" in changes and (changes["amount"] is None or changes["amount"] <= 0):
        raise HTTPException(400, "مبلغ باید عددی مثبت باشد")
    row.update({k: v for k, v in changes.items() if k in ("amount", "date")})
    with db_transaction(db):
        db.execute("UPDATE debt_payments SET amount=?, date=? WHERE id=?", (row["amount"], row["date"], payment_id))
        _sync_debt_status(db, debt_id)
    return {"ok": True}


@router.delete("/debts/{debt_id}/payments/{payment_id}")
def delete_debt_payment(debt_id: int, payment_id: int, db: sqlite3.Connection = Depends(get_db)):
    _or_404(db.execute("SELECT id FROM debt_payments WHERE id = ? AND debt_id = ?", (payment_id, debt_id)).fetchone(), "پرداخت یافت نشد")
    with db_transaction(db):
        db.execute("DELETE FROM debt_payments WHERE id = ?", (payment_id,))
        _sync_debt_status(db, debt_id)
    return {"ok": True}


# ------------------------------------------------------------------ وام و اقساط

class LoanUpdate(BaseModel):
    name: Optional[str] = None
    lender: Optional[str] = None
    principal: Optional[int] = None
    termMonths: Optional[int] = None
    installmentAmount: Optional[int] = None
    startDate: Optional[str] = None
    interestRateBps: Optional[int] = None
    accountId: Optional[int] = None
    notes: Optional[str] = None


class InstallmentUpdate(BaseModel):
    paidAmount: Optional[int] = None
    amount: Optional[int] = None
    dueDate: Optional[str] = None


@router.put("/loans/{loan_id}")
def update_loan(loan_id: int, body: LoanUpdate, db: sqlite3.Connection = Depends(get_db)):
    loan = dict(_or_404(db.execute("SELECT * FROM loans WHERE id = ?", (loan_id,)).fetchone(), "وام یافت نشد"))
    changes = body.model_dump(exclude_unset=True)
    col = {"termMonths": "term_months", "installmentAmount": "installment_amount", "startDate": "start_date",
           "interestRateBps": "interest_rate", "accountId": "account_id"}
    merged = dict(loan)
    for field, value in changes.items():
        merged[col.get(field, field)] = _clean(value)
    if not merged["name"] or not merged["lender"]:
        raise HTTPException(400, "نام وام و طلبکار الزامی است")
    if merged["term_months"] is None or merged["term_months"] < 1 or not merged["installment_amount"] or merged["installment_amount"] <= 0:
        raise HTTPException(400, "تعداد اقساط و مبلغ قسط باید عددی مثبت باشد")

    schedule_changed = any(merged[k] != loan[k] for k in ("term_months", "installment_amount", "start_date"))
    with db_transaction(db):
        if schedule_changed:
            has_payments = db.execute(
                "SELECT COUNT(*) AS c FROM installments WHERE loan_id = ? AND paid_amount > 0", (loan_id,)
            ).fetchone()["c"]
            if has_payments:
                raise HTTPException(400, "برای تغییر تعداد/مبلغ/تاریخ شروع اقساط، ابتدا پرداخت‌های ثبت‌شده را صفر کنید")
            db.execute("DELETE FROM installments WHERE loan_id = ?", (loan_id,))
            for inst in generate_installment_schedule(loan_id, merged["principal"], merged["term_months"],
                                                       merged["installment_amount"], merged["start_date"]):
                db.execute(
                    "INSERT INTO installments (loan_id, installment_number, due_date, amount, status) VALUES (?, ?, ?, ?, 'upcoming')",
                    (loan_id, inst["installment_number"], inst["due_date"], inst["amount"]),
                )
        db.execute(
            "UPDATE loans SET name=?, lender=?, principal=?, interest_rate=?, term_months=?, installment_amount=?, "
            "start_date=?, account_id=?, notes=? WHERE id=?",
            (merged["name"], merged["lender"], merged["principal"], merged["interest_rate"], merged["term_months"],
             merged["installment_amount"], merged["start_date"], merged["account_id"], merged["notes"], loan_id),
        )
    return {"ok": True}


@router.put("/loans/installments/{installment_id}")
def update_installment(installment_id: int, body: InstallmentUpdate, db: sqlite3.Connection = Depends(get_db)):
    inst = dict(_or_404(db.execute("SELECT * FROM installments WHERE id = ?", (installment_id,)).fetchone(), "قسط یافت نشد"))
    changes = body.model_dump(exclude_unset=True)
    amount = changes.get("amount", inst["amount"])
    paid = changes.get("paidAmount", inst["paid_amount"])
    due = changes.get("dueDate") or inst["due_date"]
    if amount is None or amount <= 0 or paid is None or paid < 0:
        raise HTTPException(400, "مبلغ‌ها باید عددی معتبر باشند")
    status = compute_installment_status(amount, paid, due, date.today().isoformat())
    db.execute("UPDATE installments SET amount=?, paid_amount=?, due_date=?, status=? WHERE id=?",
               (amount, paid, due, status, installment_id))
    db.commit()
    return {"ok": True}


# ----------------------------------------------------------- مشتری / فروش قسطی

class SaleUpdate(BaseModel):
    customerId: Optional[int] = None
    date: Optional[str] = None
    itemAmount: Optional[int] = None
    discount: Optional[int] = None
    downPayment: Optional[int] = None
    installmentCount: Optional[int] = None
    paymentTerms: Optional[str] = None


@router.put("/customers/{customer_id}")
def update_customer(customer_id: int, body: CustomerIn, db: sqlite3.Connection = Depends(get_db)):
    _or_404(db.execute("SELECT id FROM customers WHERE id = ?", (customer_id,)).fetchone(), "مشتری یافت نشد")
    db.execute("UPDATE customers SET name=?, phone=?, description=? WHERE id=?",
               (body.name, body.phone, body.description, customer_id))
    db.commit()
    return {"ok": True}


@router.put("/installment-sales/{sale_id}")
def update_sale(sale_id: int, body: SaleUpdate, db: sqlite3.Connection = Depends(get_db)):
    sale = dict(_or_404(db.execute("SELECT * FROM installment_sales WHERE id = ?", (sale_id,)).fetchone(), "فروش یافت نشد"))
    changes = body.model_dump(exclude_unset=True)
    col = {"customerId": "customer_id", "itemAmount": "item_amount", "downPayment": "down_payment",
           "installmentCount": "installment_count", "paymentTerms": "payment_terms"}
    for field, value in changes.items():
        sale[col.get(field, field)] = _clean(value)
    if "customerId" in changes:
        _or_404(db.execute("SELECT id FROM customers WHERE id = ?", (sale["customer_id"],)).fetchone(), "مشتری یافت نشد")
    if sale["item_amount"] is None or sale["item_amount"] <= 0 or (sale["discount"] or 0) < 0 or (sale["down_payment"] or 0) < 0:
        raise HTTPException(400, "مبلغ‌ها باید عددی معتبر باشند")
    if (sale["installment_count"] or 0) < 1:
        raise HTTPException(400, "تعداد اقساط باید حداقل ۱ باشد")
    sale["discount"] = sale["discount"] or 0
    sale["down_payment"] = sale["down_payment"] or 0
    final_amount = sale["item_amount"] - sale["discount"]
    if final_amount < 0:
        raise HTTPException(400, "تخفیف نمی‌تواند از مبلغ کالا بیشتر باشد")
    db.execute(
        "UPDATE installment_sales SET customer_id=?, date=?, item_amount=?, discount=?, final_amount=?, down_payment=?, "
        "installment_count=?, payment_terms=? WHERE id=?",
        (sale["customer_id"], sale["date"], sale["item_amount"], sale["discount"], final_amount, sale["down_payment"],
         sale["installment_count"], sale["payment_terms"], sale_id),
    )
    db.commit()
    return {"ok": True}


@router.delete("/installment-sales/{sale_id}")
def delete_sale(sale_id: int, db: sqlite3.Connection = Depends(get_db)):
    _or_404(db.execute("SELECT id FROM installment_sales WHERE id = ?", (sale_id,)).fetchone(), "فروش یافت نشد")
    with db_transaction(db):
        db.execute("DELETE FROM sale_payments WHERE sale_id = ?", (sale_id,))
        db.execute("DELETE FROM installment_sales WHERE id = ?", (sale_id,))
    return {"ok": True}


@router.put("/installment-sales/{sale_id}/payments/{payment_id}")
def update_sale_payment(sale_id: int, payment_id: int, body: PaymentUpdate, db: sqlite3.Connection = Depends(get_db)):
    row = dict(_or_404(db.execute("SELECT * FROM sale_payments WHERE id = ? AND sale_id = ?", (payment_id, sale_id)).fetchone(), "پرداخت یافت نشد"))
    changes = body.model_dump(exclude_unset=True)
    if "amount" in changes and (changes["amount"] is None or changes["amount"] <= 0):
        raise HTTPException(400, "مبلغ باید عددی مثبت باشد")
    row.update({k: v for k, v in changes.items() if k in ("amount", "date", "notes")})
    db.execute("UPDATE sale_payments SET amount=?, date=?, notes=? WHERE id=?", (row["amount"], row["date"], row["notes"], payment_id))
    db.commit()
    return {"ok": True}


@router.delete("/installment-sales/{sale_id}/payments/{payment_id}")
def delete_sale_payment(sale_id: int, payment_id: int, db: sqlite3.Connection = Depends(get_db)):
    _or_404(db.execute("SELECT id FROM sale_payments WHERE id = ? AND sale_id = ?", (payment_id, sale_id)).fetchone(), "پرداخت یافت نشد")
    db.execute("DELETE FROM sale_payments WHERE id = ?", (payment_id,))
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------- برچسب / بودجه / انتقال

class BudgetUpdate(BaseModel):
    amount: int


class TransferUpdate(BaseModel):
    fromAccountId: Optional[int] = None
    toAccountId: Optional[int] = None
    amount: Optional[int] = None
    date: Optional[str] = None
    description: Optional[str] = None


@router.put("/tags/{tag_id}")
def update_tag(tag_id: int, body: TagIn, db: sqlite3.Connection = Depends(get_db)):
    _or_404(db.execute("SELECT id FROM tags WHERE id = ?", (tag_id,)).fetchone(), "برچسب یافت نشد")
    try:
        db.execute("UPDATE tags SET name=?, color=? WHERE id=?", (body.name, body.color, tag_id))
        db.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(409, "این برچسب از قبل وجود دارد")
    return {"ok": True}


@router.put("/budgets/{budget_id}")
def update_budget(budget_id: int, body: BudgetUpdate, db: sqlite3.Connection = Depends(get_db)):
    _or_404(db.execute("SELECT id FROM budgets WHERE id = ?", (budget_id,)).fetchone(), "بودجه یافت نشد")
    if body.amount < 0:
        raise HTTPException(400, "مبلغ بودجه نمی‌تواند منفی باشد")
    db.execute("UPDATE budgets SET amount=? WHERE id=?", (body.amount, budget_id))
    db.commit()
    return {"ok": True}


@router.put("/transfers/{transfer_id}")
def update_transfer(transfer_id: str, body: TransferUpdate, db: sqlite3.Connection = Depends(get_db)):
    rows = [dict(r) for r in db.execute("SELECT * FROM transactions WHERE transfer_id = ? ORDER BY amount", (transfer_id,))]
    if len(rows) != 2:
        raise HTTPException(404, "انتقال یافت نشد")
    out_row, in_row = rows[0], rows[1]          # مبدأ: مبلغ منفی، مقصد: مبلغ مثبت
    ch = body.model_dump(exclude_unset=True)
    from_id = ch.get("fromAccountId", out_row["account_id"])
    to_id = ch.get("toAccountId", in_row["account_id"])
    amount = abs(ch.get("amount", in_row["amount"]))
    if from_id == to_id:
        raise HTTPException(400, "حساب مبدأ و مقصد نمی‌توانند یکسان باشند")
    if amount <= 0:
        raise HTTPException(400, "مبلغ باید عددی مثبت باشد")
    for acc in (from_id, to_id):
        _or_404(db.execute("SELECT id FROM accounts WHERE id = ?", (acc,)).fetchone(), "حساب یافت نشد")
    when = ch.get("date") or out_row["transaction_date"]
    with db_transaction(db):
        out_desc = ch["description"] if ch.get("description") else out_row["description"]
        in_desc = ch["description"] if ch.get("description") else in_row["description"]
        db.execute("UPDATE transactions SET account_id=?, amount=?, transaction_date=?, description=? WHERE id=?",
                   (from_id, -amount, when, out_desc, out_row["id"]))
        db.execute("UPDATE transactions SET account_id=?, amount=?, transaction_date=?, description=? WHERE id=?",
                   (to_id, amount, when, in_desc, in_row["id"]))
    return {"ok": True}


# ------------------------------------------------- خواندن جزئیات برای فرم‌های ویرایش

@router.get("/transfers/{transfer_id}")
def get_transfer(transfer_id: str, db: sqlite3.Connection = Depends(get_db)):
    rows = [dict(r) for r in db.execute("SELECT * FROM transactions WHERE transfer_id = ? ORDER BY amount", (transfer_id,))]
    if len(rows) != 2:
        raise HTTPException(404, "انتقال یافت نشد")
    out_row, in_row = rows
    return {"transfer_id": transfer_id, "fromAccountId": out_row["account_id"], "toAccountId": in_row["account_id"],
            "amount": in_row["amount"], "date": out_row["transaction_date"], "description": out_row["description"]}


@router.get("/budgets/item/{budget_id}")
def get_budget(budget_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = _or_404(db.execute(
        "SELECT b.*, c.name AS category_name FROM budgets b JOIN categories c ON c.id = b.category_id WHERE b.id = ?",
        (budget_id,)).fetchone(), "بودجه یافت نشد")
    return dict(row)
