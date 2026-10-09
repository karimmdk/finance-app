import os
import time
import sqlite3
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from app.deps import get_db
from app.schemas import TransactionIn, TransactionUpdate, QuickUpdate, BulkUpdateIn, BulkDeleteIn
from app.lib.description_parser import parse_transaction_description
from app.lib.recurring_detection import detect_recurring_series
from app.lib.anomaly_detection import compute_category_stats, is_anomalous_amount
from app.lib.reparse_descriptions import reparse_all_descriptions
from app.importers.generic_bank_xlsx import parse_generic_bank_xlsx
from app.lib import csv_exchange
from app.importers.import_orchestrator import run_import, undo_import_batch
from app.lib.duplicate_detection import detect_duplicate
import json
from datetime import date

from pydantic import BaseModel

router = APIRouter()

ATTACHMENTS_DIR = Path(os.environ.get("FINANCE_ATTACHMENTS_DIR") or (Path(__file__).resolve().parent.parent.parent / "data" / "attachments"))


class ReparseIn(BaseModel):
    force: bool = False


class BulkExcludeIn(BaseModel):
    ids: list[int]
    excluded: bool = True


def attach_tags(db: sqlite3.Connection, transactions: list[dict]) -> list[dict]:
    if not transactions:
        return transactions
    ids = [t["id"] for t in transactions]
    placeholders = ",".join("?" * len(ids))
    tag_rows = db.execute(
        f"""SELECT tt.transaction_id as txnId, t.id, t.name, t.color
            FROM transaction_tags tt JOIN tags t ON t.id = tt.tag_id
            WHERE tt.transaction_id IN ({placeholders})""",
        ids,
    ).fetchall()
    by_txn: dict[int, list[dict]] = {}
    for row in tag_rows:
        by_txn.setdefault(row["txnId"], []).append({"id": row["id"], "name": row["name"], "color": row["color"]})
    for t in transactions:
        t["tags"] = by_txn.get(t["id"], [])
    return transactions


def _txn_to_camel(t) -> dict:
    """
    فرانت‌اند React (بدون تغییر از نسخه Node) انتظار camelCase دارد (transactionDate، ...) —
    این تابع مرز سازگاری بین NormalizedTransaction پایتونی (snake_case) و پاسخ JSON است.
    """
    return {
        "accountId": t.account_id,
        "transactionDate": t.transaction_date,
        "transactionTime": t.transaction_time,
        "amount": t.amount,
        "type": t.type,
        "description": t.description,
        "documentNumber": t.document_number,
        "balanceAfter": t.balance_after,
        "sourceRowNumber": t.source_row_number,
        "rawTransactionType": t.raw_transaction_type,
    }


def _dup_to_camel(d: dict) -> dict:
    result = {"status": d["status"]}
    if "matched_transaction_id" in d:
        result["matchedTransactionId"] = d["matched_transaction_id"]
    if "reason" in d:
        result["reason"] = d["reason"]
    return result


# ---------- فهرست + جستجو/فیلتر ----------
@router.get("")
def list_transactions(accountId: int | None = None, categoryId: int | None = None, personId: int | None = None,
                       type: str | None = None, bankName: str | None = None, q: str | None = None,
                       date_from: str | None = Query(default=None, alias="from"),
                       date_to: str | None = Query(default=None, alias="to"),
                       limit: int = 200, offset: int = 0,
                       db: sqlite3.Connection = Depends(get_db)):
    clauses, params = [], []
    if accountId: clauses.append("account_id = ?"); params.append(accountId)
    if categoryId: clauses.append("category_id = ?"); params.append(categoryId)
    if personId: clauses.append("person_id = ?"); params.append(personId)
    if type: clauses.append("type = ?"); params.append(type)
    if bankName: clauses.append("bank_name = ?"); params.append(bankName)
    if date_from: clauses.append("transaction_date >= ?"); params.append(date_from)
    if date_to: clauses.append("transaction_date <= ?"); params.append(date_to)
    if q:
        clauses.append("(description LIKE ? OR document_number LIKE ? OR counterparty LIKE ? OR card_number LIKE ? OR iban LIKE ? OR bank_name LIKE ? OR reason LIKE ?)")
        like = f"%{q}%"
        params.extend([like] * 7)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    row_limit = min(limit, 5000)
    rows = [dict(r) for r in db.execute(
        f"SELECT * FROM transactions {where} ORDER BY transaction_date DESC, id DESC LIMIT ? OFFSET ?", params + [row_limit, offset]
    )]
    total = db.execute(f"SELECT COUNT(*) as c FROM transactions {where}", params).fetchone()["c"]
    return {"items": attach_tags(db, rows), "total": total, "offset": offset, "limit": row_limit}


# نکته مسیریابی: این routeها باید قبل از "/{transaction_id}" ثبت شوند (همان رگرسیونی که در
# نسخه Node پیدا و رفع شد — FastAPI هم به همین ترتیب مسیرها را تطبیق می‌دهد).
@router.get("/recurring")
def get_recurring(db: sqlite3.Connection = Depends(get_db)):
    rows = [
        {"account_id": r["account_id"], "type": r["type"], "amount": r["amount"],
         "description": r["description"], "transaction_date": r["transaction_date"]}
        for r in db.execute(
            "SELECT account_id, type, amount, description, transaction_date FROM transactions "
            "WHERE type IN ('income','expense') AND excluded_from_analysis = 0 ORDER BY transaction_date"
        )
    ]
    today = date.today().isoformat()
    return detect_recurring_series(rows, today)


@router.get("/anomalies")
def get_anomalies(months: int = 6, db: sqlite3.Connection = Depends(get_db)):
    rows = [dict(r) for r in db.execute(
        """SELECT id, category_id, amount, transaction_date, description
           FROM transactions
           WHERE type = 'expense' AND category_id IS NOT NULL AND excluded_from_analysis = 0
             AND transaction_date >= date('now', '-' || ? || ' months')
           ORDER BY category_id""",
        (months,),
    )]
    by_category: dict[int, list[dict]] = {}
    for r in rows:
        by_category.setdefault(r["category_id"], []).append(r)

    anomalies = []
    for category_id, group in by_category.items():
        for r in group:
            others = [g["amount"] for g in group if g["id"] != r["id"]]
            stats = compute_category_stats(others)
            if is_anomalous_amount(r["amount"], stats):
                anomalies.append({
                    "id": r["id"], "categoryId": category_id, "amount": r["amount"],
                    "transactionDate": r["transaction_date"], "description": r["description"],
                    "categoryAvg": round(stats["avg"]),
                })
    return sorted(anomalies, key=lambda a: a["transactionDate"], reverse=True)


@router.post("/reparse-descriptions")
def reparse_descriptions(body: ReparseIn = ReparseIn(), db: sqlite3.Connection = Depends(get_db)):
    return reparse_all_descriptions(db, body.force)


@router.post("/bulk-update")
def bulk_update(body: BulkUpdateIn, db: sqlite3.Connection = Depends(get_db)):
    placeholders = ",".join("?" * len(body.ids))
    if body.categoryId is not None:
        db.execute(f"UPDATE transactions SET category_id = ? WHERE id IN ({placeholders})", [body.categoryId] + body.ids)
    if body.addTagId is not None:
        for txn_id in body.ids:
            db.execute("INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (txn_id, body.addTagId))
    db.commit()
    return {"ok": True, "count": len(body.ids)}


@router.post("/bulk-delete")
def bulk_delete(body: BulkDeleteIn, db: sqlite3.Connection = Depends(get_db)):
    placeholders = ",".join("?" * len(body.ids))
    db.execute(f"DELETE FROM transaction_tags WHERE transaction_id IN ({placeholders})", body.ids)
    db.execute(f"DELETE FROM transaction_attachments WHERE transaction_id IN ({placeholders})", body.ids)
    db.execute(f"DELETE FROM transactions WHERE id IN ({placeholders})", body.ids)
    db.commit()
    return {"ok": True, "count": len(body.ids)}


@router.post("/bulk-exclude")
def bulk_exclude(body: BulkExcludeIn, db: sqlite3.Connection = Depends(get_db)):
    """
    استثنا/بازگرداندن گروهی از آنالیز — برای مواردی مثل واریز بین کارت‌های خودِ کاربر یا «باکس»
    که پول واقعاً جابه‌جا شده (موجودی حساب دست‌نخورده می‌ماند) ولی نباید در گزارش‌ها/داشبورد/
    تشخیص تکرارشونده و غیرعادی حساب شود.
    """
    placeholders = ",".join("?" * len(body.ids))
    db.execute(
        f"UPDATE transactions SET excluded_from_analysis = ? WHERE id IN ({placeholders})",
        [int(body.excluded)] + body.ids,
    )
    db.commit()
    return {"ok": True, "count": len(body.ids)}


# ---------- پیوست‌ها (باید قبل از "/{transaction_id}" باشد چون "/attachments/..." الگوی جدا دارد) ----------
@router.get("/attachments/{attachment_id}/file")
def get_attachment_file(attachment_id: int, db: sqlite3.Connection = Depends(get_db)):
    att = db.execute("SELECT * FROM transaction_attachments WHERE id = ?", (attachment_id,)).fetchone()
    if not att:
        raise HTTPException(404, "پیوست یافت نشد")
    file_path = ATTACHMENTS_DIR / att["stored_path"]
    if not file_path.exists():
        raise HTTPException(404, "فایل روی دیسک یافت نشد")
    return FileResponse(file_path, media_type=att["mime_type"] or "application/octet-stream", filename=att["file_name"])


@router.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: int, db: sqlite3.Connection = Depends(get_db)):
    att = db.execute("SELECT * FROM transaction_attachments WHERE id = ?", (attachment_id,)).fetchone()
    if att:
        file_path = ATTACHMENTS_DIR / att["stored_path"]
        if file_path.exists():
            file_path.unlink()
        db.execute("DELETE FROM transaction_attachments WHERE id = ?", (attachment_id,))
        db.commit()
    return {"ok": True}


# ---------- Import Workflow ----------
def _is_csv(filename: str | None, content: bytes) -> bool:
    """CSV خروجی خود برنامه یا فایل Excel؟ (xlsx = zip با امضای PK، xls قدیمی = OLE با امضای D0CF)"""
    if (filename or "").lower().endswith(".csv"):
        return True
    return content[:2] not in (b"PK", b"\xd0\xcf")


def _csv_parse_transactions(db, content: bytes, account_id: int) -> dict:
    try:
        if csv_exchange.sniff_csv_kind(content) == "taxonomy":
            raise csv_exchange.CsvFormatError(
                "این فایل فهرست دسته‌بندی/برچسب است، نه تراکنش؛ آن را از «تنظیمات و پشتیبان‌گیری ← درون‌ریزی دسته‌بندی‌ها و برچسب‌ها» وارد کنید")
        return csv_exchange.parse_transactions_csv(content, db, account_id)
    except csv_exchange.CsvFormatError as e:
        raise HTTPException(400, f"خطا در خواندن فایل: {e}")


def _csv_preview(db, content: bytes, account_id: int, update_existing: bool) -> dict:
    parsed = _csv_parse_transactions(db, content, account_id)
    return csv_exchange.preview_transactions_csv(db, parsed, update_existing)


def _csv_commit(db, content: bytes, account_id: int, file_name: str, decisions: str | None,
                apply_rules: bool, update_existing: bool) -> dict:
    parsed = _csv_parse_transactions(db, content, account_id)
    decisions_map = {int(k): v for k, v in json.loads(decisions).items()} if decisions else None
    try:
        return csv_exchange.commit_transactions_csv(db, parsed, file_name, decisions_map, apply_rules, update_existing)
    except Exception as e:
        raise HTTPException(500, f"Import ناموفق بود و به طور کامل rollback شد: {e}")


@router.post("/import/preview")
async def import_preview(file: UploadFile = File(...), accountId: int = Form(...),
                          updateExisting: bool = Form(default=True), db: sqlite3.Connection = Depends(get_db)):
    content = await file.read()
    if _is_csv(file.filename, content):
        return _csv_preview(db, content, accountId, updateExisting)
    try:
        parsed = parse_generic_bank_xlsx(content, accountId)
    except Exception as e:
        raise HTTPException(400, f"خطا در خواندن فایل: {e}")

    existing = [dict(r) for r in db.execute(
        """SELECT id, account_id, transaction_date, amount, type, document_number, description
           FROM transactions WHERE account_id = ?""",
        (accountId,),
    )]

    preview = []
    for idx, t in enumerate(parsed["transactions"]):
        dup = {"status": "new"} if t.type == "adjustment" else detect_duplicate(t, existing)
        preview.append({"index": idx, "transaction": _txn_to_camel(t), "duplicateResult": _dup_to_camel(dup)})

    summary = {
        "total": len(preview),
        "new": sum(1 for p in preview if p["duplicateResult"]["status"] == "new"),
        "definiteDuplicate": sum(1 for p in preview if p["duplicateResult"]["status"] == "definite_duplicate"),
        "probableDuplicate": sum(1 for p in preview if p["duplicateResult"]["status"] == "probable_duplicate"),
        "adjustment": sum(1 for p in preview if p["transaction"]["type"] == "adjustment"),
    }
    return {"headerMeta": parsed["header_meta"], "issues": parsed["issues"], "preview": preview, "summary": summary}


@router.post("/import/commit", status_code=201)
async def import_commit(file: UploadFile = File(...), accountId: int = Form(...),
                         decisions: str | None = Form(default=None), applyRules: bool = Form(default=False),
                         updateExisting: bool = Form(default=True), db: sqlite3.Connection = Depends(get_db)):
    content = await file.read()
    if _is_csv(file.filename, content):
        return _csv_commit(db, content, accountId, file.filename, decisions, applyRules, updateExisting)
    try:
        parsed = parse_generic_bank_xlsx(content, accountId)
    except Exception as e:
        raise HTTPException(400, f"خطا در خواندن فایل: {e}")

    decisions_map = {int(k): v for k, v in json.loads(decisions).items()} if decisions else None
    try:
        summary = run_import(db, accountId, file.filename, "generic-bank-xlsx",
                              parsed["transactions"], parsed["issues"], decisions_map, applyRules)
    except Exception as e:
        raise HTTPException(500, f"Import ناموفق بود و به طور کامل rollback شد: {e}")
    return summary


@router.post("/import/{batch_id}/undo")
def import_undo(batch_id: int, db: sqlite3.Connection = Depends(get_db)):
    undo_import_batch(db, batch_id)
    return {"ok": True}


@router.get("/import/batches")
def import_batches(db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute("SELECT * FROM import_batches ORDER BY id DESC")]


# ---------- CRUD تراکنش تکی (باید بعد از routeهای اختصاصی بالا ثبت شود) ----------
@router.get("/{transaction_id}")
def get_transaction(transaction_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if not row:
        raise HTTPException(404, "تراکنش یافت نشد")
    txn = dict(row)
    txn["tags"] = [dict(r) for r in db.execute(
        "SELECT t.* FROM tags t JOIN transaction_tags tt ON tt.tag_id = t.id WHERE tt.transaction_id = ?",
        (transaction_id,),
    )]
    return txn


@router.get("/{transaction_id}/attachments")
def list_attachments(transaction_id: int, db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute(
        "SELECT id, file_name, mime_type, size_bytes, created_at FROM transaction_attachments WHERE transaction_id = ?",
        (transaction_id,),
    )]


@router.post("/{transaction_id}/attachments", status_code=201)
async def upload_attachment(transaction_id: int, file: UploadFile = File(...), db: sqlite3.Connection = Depends(get_db)):
    txn = db.execute("SELECT id FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if not txn:
        raise HTTPException(404, "تراکنش یافت نشد")

    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    safe_ext = Path(file.filename).suffix[:10]
    stored_name = f"{transaction_id}-{int(time.time() * 1000)}{safe_ext}"
    content = await file.read()
    (ATTACHMENTS_DIR / stored_name).write_bytes(content)

    cur = db.execute(
        "INSERT INTO transaction_attachments (transaction_id, file_name, stored_path, mime_type, size_bytes) VALUES (?, ?, ?, ?, ?)",
        (transaction_id, file.filename, stored_name, file.content_type, len(content)),
    )
    db.commit()
    return {"id": cur.lastrowid}


@router.post("", status_code=201)
def create_transaction(body: TransactionIn, db: sqlite3.Connection = Depends(get_db)):
    auto = parse_transaction_description(body.description)
    cur = db.execute(
        """INSERT INTO transactions
             (account_id, transaction_date, transaction_time, amount, type, description, category_id, person_id, notes,
              counterparty, card_number, iban, bank_name, reason, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual')""",
        (body.accountId, body.transactionDate, body.transactionTime, body.amount, body.type, body.description,
         body.categoryId, body.personId, body.notes,
         body.counterparty or auto["counterparty"], body.cardNumber or auto["card_number"],
         body.iban or auto["iban"], body.bankName or auto["bank_name"], body.reason or auto["reason"]),
    )
    txn_id = cur.lastrowid
    if body.tagIds:
        for tag_id in body.tagIds:
            db.execute("INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (txn_id, tag_id))
    db.commit()
    return {"id": txn_id}


@router.put("/{transaction_id}")
def update_transaction(transaction_id: int, body: TransactionUpdate, db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "تراکنش یافت نشد")
    d = body.model_dump(exclude_unset=True)

    should_reparse = "description" in d and d["description"] != existing["description"]
    auto = parse_transaction_description(d.get("description")) if should_reparse else None

    db.execute(
        """UPDATE transactions SET
             transaction_date = COALESCE(?, transaction_date),
             amount = COALESCE(?, amount),
             type = COALESCE(?, type),
             description = COALESCE(?, description),
             category_id = ?, person_id = ?, notes = ?,
             counterparty = ?, card_number = ?, iban = ?, bank_name = ?, reason = ?,
             raw_transaction_type = COALESCE(?, raw_transaction_type),
             excluded_from_analysis = COALESCE(?, excluded_from_analysis),
             updated_at = datetime('now')
           WHERE id = ?""",
        (d.get("transactionDate"), d.get("amount"), d.get("type"), d.get("description"),
         d.get("categoryId", existing["category_id"]), d.get("personId", existing["person_id"]),
         d.get("notes", existing["notes"]),
         d.get("counterparty") or (auto["counterparty"] if auto else existing["counterparty"]),
         d.get("cardNumber") or (auto["card_number"] if auto else existing["card_number"]),
         d.get("iban") or (auto["iban"] if auto else existing["iban"]),
         d.get("bankName") or (auto["bank_name"] if auto else existing["bank_name"]),
         d.get("reason") or (auto["reason"] if auto else existing["reason"]),
         d.get("rawTransactionType"),
         int(d["excludedFromAnalysis"]) if "excludedFromAnalysis" in d else None,
         transaction_id),
    )

    if "tagIds" in d:
        db.execute("DELETE FROM transaction_tags WHERE transaction_id = ?", (transaction_id,))
        for tag_id in (d["tagIds"] or []):
            db.execute("INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (transaction_id, tag_id))

    db.commit()
    return {"ok": True}


@router.patch("/{transaction_id}/quick")
def quick_update(transaction_id: int, body: QuickUpdate, db: sqlite3.Connection = Depends(get_db)):
    d = body.model_dump(exclude_unset=True)
    if "categoryId" in d:
        db.execute("UPDATE transactions SET category_id = ? WHERE id = ?", (d["categoryId"], transaction_id))
    if "personId" in d:
        db.execute("UPDATE transactions SET person_id = ? WHERE id = ?", (d["personId"], transaction_id))
    if "excludedFromAnalysis" in d:
        db.execute("UPDATE transactions SET excluded_from_analysis = ? WHERE id = ?", (int(d["excludedFromAnalysis"]), transaction_id))
    if "tagIds" in d:
        db.execute("DELETE FROM transaction_tags WHERE transaction_id = ?", (transaction_id,))
        for tag_id in (d["tagIds"] or []):
            db.execute("INSERT OR IGNORE INTO transaction_tags (transaction_id, tag_id) VALUES (?, ?)", (transaction_id, tag_id))
    db.commit()
    return {"ok": True}


@router.delete("/{transaction_id}")
def delete_transaction(transaction_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM transaction_tags WHERE transaction_id = ?", (transaction_id,))
    db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    db.commit()
    return {"ok": True}
