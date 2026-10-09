"""تشخیص تراکنش‌های تکرارشونده — معادل src/lib/recurring-detection.ts."""
from datetime import date as date_cls, timedelta
from collections import defaultdict


def _days_between(a: str, b: str) -> int:
    ay, am, ad = (int(p) for p in a.split("-"))
    by, bm, bd = (int(p) for p in b.split("-"))
    return (date_cls(by, bm, bd) - date_cls(ay, am, ad)).days


def _add_days(iso: str, days: int) -> str:
    y, m, d = (int(p) for p in iso.split("-"))
    return (date_cls(y, m, d) + timedelta(days=days)).isoformat()


def detect_recurring_series(transactions: list[dict], today_iso: str, min_occurrences: int = 2,
                             min_interval_days: int = 25, max_interval_days: int = 35) -> list[dict]:
    """
    transactions: [{"account_id":, "type":, "amount":, "description":, "transaction_date":}, ...]
    گروه‌بندی بر اساس (account_id, type, amount, description) دقیقاً یکسان؛ اگر حداقل نیمی از
    فاصله‌های زمانی بین وقوع‌ها در بازه ۲۵-۳۵ روز باشد، به‌عنوان سری تکرارشونده ماهانه شناخته می‌شود.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for t in transactions:
        if t["type"] not in ("income", "expense"):
            continue
        key = (t["account_id"], t["type"], t["amount"], t.get("description") or "")
        groups[key].append(t)

    results = []
    for group in groups.values():
        if len(group) < min_occurrences:
            continue
        sorted_group = sorted(group, key=lambda t: t["transaction_date"])
        intervals = [
            _days_between(sorted_group[i - 1]["transaction_date"], sorted_group[i]["transaction_date"])
            for i in range(1, len(sorted_group))
        ]
        monthly = [d for d in intervals if min_interval_days <= d <= max_interval_days]
        if not monthly or len(monthly) < len(intervals) * 0.5:
            continue

        avg_interval = round(sum(monthly) / len(monthly))
        last_date = sorted_group[-1]["transaction_date"]
        next_expected = _add_days(last_date, avg_interval)
        days_until_next = _days_between(today_iso, next_expected)

        sample = sorted_group[0]
        results.append({
            "account_id": sample["account_id"],
            "type": sample["type"],
            "amount": sample["amount"],
            "description": sample.get("description"),
            "occurrence_count": len(sorted_group),
            "average_interval_days": avg_interval,
            "last_date": last_date,
            "next_expected_date": next_expected,
            "days_until_next": days_until_next,
        })

    return sorted(results, key=lambda r: r["days_until_next"])
