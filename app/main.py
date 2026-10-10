"""
ساخت FastAPI app از یک DB connection آماده — معادل src/server/app.ts نسخه Node، جدا از
راه‌اندازی سرور واقعی (uvicorn.run) تا در تست‌های integration بدون باز کردن پورت واقعی قابل استفاده باشد.
"""
import sqlite3
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.requests import Request

from app.routes import accounts, transactions, transfers, debts, loans, rules, dashboard, budgets, backup, ai, saved_filters, manage
from app.routes.people_categories_tags import people_router, categories_router, tags_router
from app.routes.customers_sales import customers_router, sales_router


def create_app(db: sqlite3.Connection, static_dir: str | None = None, db_path: str | None = None) -> FastAPI:
    app = FastAPI(title="Finance API")
    app.state.db = db
    app.state.db_path = db_path

    # این اپلیکیشن local-first و تک‌کاربره است (بدون login) — CORS باز است چون فقط از
    # localhost/فایل استاتیک همین برنامه استفاده می‌شود، نه یک سرویس چندکاربره عمومی.
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    # نکته سازگاری مهم: فرانت‌اند React (بدون تغییر از نسخه Node) در src/ui/api.ts فرض می‌کند
    # خطاها به شکل {"error": ...} برمی‌گردند (همان قرارداد Express+Zod). فرمت پیش‌فرض FastAPI
    # {"detail": ...} است — بدون این handlerها پیام خطا در UI به‌سادگی ناپدید می‌شد.
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=400, content={"error": exc.errors()})

    app.include_router(accounts.router, prefix="/api/accounts")
    app.include_router(transactions.router, prefix="/api/transactions")
    app.include_router(transfers.router, prefix="/api/transfers")
    app.include_router(people_router, prefix="/api/people")
    app.include_router(categories_router, prefix="/api/categories")
    app.include_router(tags_router, prefix="/api/tags")
    app.include_router(debts.router, prefix="/api/debts")
    app.include_router(loans.router, prefix="/api/loans")
    app.include_router(customers_router, prefix="/api/customers")
    app.include_router(sales_router, prefix="/api/installment-sales")
    app.include_router(rules.router, prefix="/api/rules")
    app.include_router(dashboard.router, prefix="/api/dashboard")
    app.include_router(budgets.router, prefix="/api/budgets")
    app.include_router(backup.router, prefix="/api/backup")
    app.include_router(ai.router, prefix="/api/ai")
    app.include_router(manage.router, prefix="/api")
    app.include_router(saved_filters.router, prefix="/api/saved-filters")

    @app.get("/api/health")
    def health():
        return {"ok": True}

    if static_dir and Path(static_dir).exists():
        app.mount("/assets", StaticFiles(directory=str(Path(static_dir) / "assets")), name="assets")

        @app.get("/")
        def spa_root():
            return FileResponse(str(Path(static_dir) / "index.html"))

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str):
            return FileResponse(str(Path(static_dir) / "index.html"))

    return app
