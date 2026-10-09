"""تشخیص تراکنش غیرعادی — معادل src/lib/anomaly-detection.ts. آماری، deterministic، بدون AI."""
import math


def compute_category_stats(amounts: list[int]) -> dict:
    if not amounts:
        return {"avg": 0, "stddev": 0, "count": 0}
    avg = sum(amounts) / len(amounts)
    variance = sum((a - avg) ** 2 for a in amounts) / len(amounts)
    return {"avg": avg, "stddev": math.sqrt(variance), "count": len(amounts)}


def is_anomalous_amount(amount: int, stats: dict, min_sample_size: int = 3) -> bool:
    """
    نیاز به حداقل ۳ تراکنش قبلی در دسته‌بندی دارد. آستانه: بزرگ‌تر از میانگین+۲×انحراف‌معیار
    (وقتی پراکندگی معنادار است) و همزمان حداقل ۱.۵ برابر میانگین (جلوگیری از پرچم‌زدن نوسانات جزئی).
    """
    if stats["count"] < min_sample_size or stats["avg"] <= 0:
        return False
    threshold = stats["avg"] + 2 * stats["stddev"] if stats["stddev"] > 0 else stats["avg"] * 1.5
    return amount > threshold and amount > stats["avg"] * 1.5
