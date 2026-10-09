import sqlite3
from datetime import date
from fastapi import APIRouter, Depends, Query
from app.deps import get_db
from app.lib.balance import calculate_total_balance, calculate_period_totals
from app.lib.loan import get_upcoming_installments
from app.lib.jalali import jalali_year_range, iso_to_jalali

router = APIRouter()


@router.get("/summary")
def dashboard_summary(db: sqlite3.Connection = Depends(get_db)):
    today = date.today().isoformat()
    month_start = today[:8] + "01"
    total_balance = calculate_total_balance(db)
    month_totals = calculate_period_totals(db, month_start, today)
    upcoming = get_upcoming_installments(db, 30, today)
    open_debts = [dict(r) for r in db.execute(
        "SELECT kind, SUM(original_amount) as total, SUM(paid_amount) as paid FROM debts WHERE status = 'open' GROUP BY kind"
    )]
    return {
        "totalBalance": total_balance,
        "currentMonth": month_totals,
        "upcomingInstallmentsCount": len(upcoming),
        "upcomingInstallmentsTotal": sum(i["amount"] - i["paid_amount"] for i in upcoming),
        "debts": open_debts,
    }


@router.get("/by-category")
def by_category(date_from: str = Query(alias="from"), date_to: str = Query(alias="to"),
                 type: str = "expense", db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute(
        """SELECT c.id as categoryId, c.name as categoryName, SUM(t.amount) as total
           FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
           WHERE t.transaction_date BETWEEN ? AND ? AND t.type = ? AND t.excluded_from_analysis = 0
           GROUP BY t.category_id ORDER BY total DESC""",
        (date_from, date_to, type),
    )]


@router.get("/monthly-trend")
def monthly_trend(months: int = 6, db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute(
        """SELECT strftime('%Y-%m', transaction_date) as month,
                  SUM(CASE WHEN type='income' THEN amount ELSE 0 END) as income,
                  SUM(CASE WHEN type='expense' THEN amount ELSE 0 END) as expense
           FROM transactions
           WHERE transaction_date >= date('now', '-' || ? || ' months') AND excluded_from_analysis = 0
           GROUP BY month ORDER BY month""",
        (months,),
    )]


@router.get("/category-trend/{category_id}")
def category_trend(category_id: int, months: int = 12, db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute(
        """SELECT strftime('%Y-%m', transaction_date) as month, SUM(amount) as total
           FROM transactions
           WHERE category_id = ? AND type = 'expense' AND excluded_from_analysis = 0
             AND transaction_date >= date('now', '-' || ? || ' months')
           GROUP BY month ORDER BY month""",
        (category_id, months),
    )]


@router.get("/by-tag")
def by_tag(date_from: str = Query(alias="from"), date_to: str = Query(alias="to"),
           type: str = "expense", db: sqlite3.Connection = Depends(get_db)):
    """
    خلاصه هزینه/درآمد بر اساس برچسب. چون یک تراکنش می‌تواند چند برچسب داشته باشد، مجموع
    ستون‌های این گزارش می‌تواند از جمع کل تراکنش‌ها بیشتر شود — این طبیعی و مورد انتظار است
    (بر خلاف دسته‌بندی که هر تراکنش فقط یک دسته دارد).
    """
    return [dict(r) for r in db.execute(
        """SELECT tag.id as tagId, tag.name as tagName, SUM(t.amount) as total
           FROM transactions t
           JOIN transaction_tags tt ON tt.transaction_id = t.id
           JOIN tags tag ON tag.id = tt.tag_id
           WHERE t.transaction_date BETWEEN ? AND ? AND t.type = ? AND t.excluded_from_analysis = 0
           GROUP BY tag.id ORDER BY total DESC""",
        (date_from, date_to, type),
    )]


@router.get("/yearly")
def yearly_report(year: int, db: sqlite3.Connection = Depends(get_db)):
    """
    گزارش سالانه بر اساس سال شمسی — روند ماهانه (بر اساس ماه شمسی، نه میلادی)، تفکیک بر اساس
    دسته‌بندی، و تفکیک بر اساس برچسب، همه برای یک سال شمسی کامل.
    """
    from_date, to_date = jalali_year_range(year)
    totals = calculate_period_totals(db, from_date, to_date)

    # روند ماهانه به تفکیک ماه شمسی — SQLite ماه شمسی نمی‌شناسد، پس این گروه‌بندی در کد انجام می‌شود
    rows = db.execute(
        """SELECT transaction_date, type, amount FROM transactions
           WHERE transaction_date BETWEEN ? AND ? AND excluded_from_analysis = 0 AND type IN ('income','expense')""",
        (from_date, to_date),
    ).fetchall()
    monthly: dict[str, dict] = {}
    for r in rows:
        month_key = iso_to_jalali(r["transaction_date"])[:7]  # "1404/07"
        if month_key not in monthly:
            monthly[month_key] = {"month": month_key, "income": 0, "expense": 0}
        monthly[month_key][r["type"]] += r["amount"]
    monthly_trend = [monthly[k] for k in sorted(monthly.keys())]

    by_category_rows = [dict(r) for r in db.execute(
        """SELECT c.id as categoryId, c.name as categoryName, SUM(t.amount) as total
           FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
           WHERE t.transaction_date BETWEEN ? AND ? AND t.type = 'expense' AND t.excluded_from_analysis = 0
           GROUP BY t.category_id ORDER BY total DESC""",
        (from_date, to_date),
    )]

    by_tag_rows = [dict(r) for r in db.execute(
        """SELECT tag.id as tagId, tag.name as tagName, SUM(t.amount) as total
           FROM transactions t
           JOIN transaction_tags tt ON tt.transaction_id = t.id
           JOIN tags tag ON tag.id = tt.tag_id
           WHERE t.transaction_date BETWEEN ? AND ? AND t.type = 'expense' AND t.excluded_from_analysis = 0
           GROUP BY tag.id ORDER BY total DESC""",
        (from_date, to_date),
    )]

    return {
        "year": year, "from": from_date, "to": to_date,
        "totalIncome": totals["income"], "totalExpense": totals["expense"], "net": totals["net"],
        "monthlyTrend": monthly_trend, "byCategory": by_category_rows, "byTag": by_tag_rows,
    }
