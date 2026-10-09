"""
جستجوی زبان طبیعی — نسخه فعلی deterministic و مبتنی بر الگوهای ساده فارسی است (بدون AI واقعی،
چون این محیط به کلید API متصل نیست). معادل src/server/routes/ai-search-engine.ts.
نقطه اتصال یک LLM واقعی در آینده: این تابع را با فراخوانی API جایگزین کنید که JSON با همین
شکل تولید کند؛ اجرای واقعی کوئری همچنان اینجا (پارامتریک، امن) باقی می‌ماند.
"""
import re
import sqlite3
from fastapi import APIRouter, Depends
from app.deps import get_db
from app.schemas import AiSearchIn

router = APIRouter()


def _parse_persian_query(query: str) -> dict:
    q = query.strip()
    months_match = re.search(r"(\d+)\s*ماه", q)
    months = int(months_match.group(1)) if months_match else None

    if re.search(r"چقدر|جمع|مجموع", q):
        category_match = re.search(r"(?:برای|روی|بابت)\s+([آ-ی\s]+?)(?:\s+خرج|\s+هزینه|$)", q)
        return {
            "intent": "total_by_category",
            "filters": {
                "categoryKeyword": category_match.group(1).strip() if category_match else None,
                "type": "income" if re.search(r"درآمد|واریز", q) else "expense",
                "months": months,
            },
        }
    return {"intent": "list_transactions", "filters": {"months": months}}


def _run_natural_language_query(db: sqlite3.Connection, query: str) -> dict:
    parsed = _parse_persian_query(query)
    months_back = parsed["filters"].get("months") or 1

    if parsed["intent"] == "total_by_category":
        category_keyword = parsed["filters"].get("categoryKeyword")
        sql = """SELECT c.name as category, SUM(t.amount) as total
                 FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
                 WHERE t.type = ? AND t.transaction_date >= date('now', '-' || ? || ' months')"""
        params = [parsed["filters"]["type"], months_back]
        if category_keyword:
            sql += " AND c.name LIKE ?"
            params.append(f"%{category_keyword}%")
        sql += " GROUP BY t.category_id ORDER BY total DESC"
        rows = [dict(r) for r in db.execute(sql, params)]
        return {"parsed": parsed, "results": rows}

    rows = [dict(r) for r in db.execute(
        "SELECT * FROM transactions WHERE transaction_date >= date('now', '-' || ? || ' months') ORDER BY transaction_date DESC LIMIT 100",
        (months_back,),
    )]
    return {"parsed": parsed, "results": rows}


@router.post("/search")
def ai_search(body: AiSearchIn, db: sqlite3.Connection = Depends(get_db)):
    return _run_natural_language_query(db, body.query)
