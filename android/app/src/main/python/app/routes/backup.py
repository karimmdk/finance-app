import json
import sqlite3
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from app.deps import get_db
from app.lib import csv_exchange

router = APIRouter()

TABLES = [
    "accounts", "transactions", "categories", "tags", "transaction_tags", "people",
    "debts", "debt_payments", "loans", "installments", "customers", "installment_sales",
    "sale_payments", "rules", "budgets", "import_batches",
]


def get_db_path(request: Request) -> str:
    return request.app.state.db_path


@router.get("/download")
def download_backup(db: sqlite3.Connection = Depends(get_db), db_path: str = Depends(get_db_path)):
    if not db_path or not Path(db_path).exists():
        raise HTTPException(404, "فایل دیتابیس یافت نشد")
    db.commit()
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")  # تغییرات WAL حتماً داخل فایل .db نوشته شود
    return FileResponse(db_path, filename=f"finance-backup-{date.today().isoformat()}.db")


@router.get("/export.json")
def export_json(db: sqlite3.Connection = Depends(get_db)):
    dump = {t: [dict(r) for r in db.execute(f"SELECT * FROM {t}")] for t in TABLES}
    content = json.dumps(dump, ensure_ascii=False, indent=2)
    headers = {"Content-Disposition": f'attachment; filename="finance-export-{date.today().isoformat()}.json"'}
    return Response(content=content, media_type="application/json", headers=headers)


@router.get("/transactions.csv")
def export_transactions_csv(db: sqlite3.Connection = Depends(get_db)):
    """
    خروجی کامل تراکنش‌ها با نام حساب، دسته‌بندی (مسیر کامل)، شخص و برچسب‌ها — قابل درون‌ریزی مجدد در همین برنامه
    (صفحه ایمپورت). جزئیات فرمت: app/lib/csv_exchange.py
    """
    headers = {"Content-Disposition": f'attachment; filename="transactions-{date.today().isoformat()}.csv"'}
    return Response(content=csv_exchange.export_transactions_csv(db), media_type="text/csv; charset=utf-8", headers=headers)


@router.get("/categories-tags.csv")
def export_categories_tags_csv(db: sqlite3.Connection = Depends(get_db)):
    """همه دسته‌بندی‌ها (با ساختار والد/فرزند) و همه برچسب‌ها، حتی موارد بدون تراکنش — قابل درون‌ریزی مجدد."""
    headers = {"Content-Disposition": f'attachment; filename="categories-tags-{date.today().isoformat()}.csv"'}
    return Response(content=csv_exchange.export_taxonomy_csv(db), media_type="text/csv; charset=utf-8", headers=headers)


@router.post("/import-categories-tags")
async def import_categories_tags_csv(file: UploadFile = File(...), db: sqlite3.Connection = Depends(get_db)):
    content = await file.read()
    try:
        if csv_exchange.sniff_csv_kind(content) != "taxonomy":
            raise csv_exchange.CsvFormatError(
                "این فایل تراکنش است، نه فهرست دسته‌بندی/برچسب؛ آن را از صفحه «ایمپورت» درون‌ریزی کنید")
        return csv_exchange.import_taxonomy_csv(db, content)
    except csv_exchange.CsvFormatError as e:
        raise HTTPException(400, str(e))
