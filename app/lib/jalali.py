"""تبدیل تاریخ شمسی/میلادی — معادل src/lib/jalali.ts نسخه Node."""
import re
import jdatetime


def jalali_to_iso(jalali_date_str: str) -> str:
    """تبدیل رشته تاریخ شمسی ("1405/04/12") به ISO میلادی ("2026-07-03")."""
    jy, jm, jd = (int(p) for p in re.split(r"[/-]", jalali_date_str.strip()))
    g = jdatetime.date(jy, jm, jd).togregorian()
    return g.isoformat()


def iso_to_jalali(iso_date_str: str) -> str:
    """تبدیل تاریخ ISO میلادی به رشته شمسی برای نمایش در UI ("1405/04/12")."""
    gy, gm, gd = (int(p) for p in iso_date_str.split("-"))
    j = jdatetime.date.fromgregorian(year=gy, month=gm, day=gd)
    return f"{j.year}/{j.month:02d}/{j.day:02d}"


def parse_bank_datetime(raw: str) -> tuple[str, str | None]:
    """پارس رشته تاریخ+ساعت فایل بانکی: "1405/04/12 12:49:59" -> (تاریخ ISO, ساعت)."""
    parts = raw.strip().split()
    date_part = parts[0]
    time_part = parts[1] if len(parts) > 1 else None
    return jalali_to_iso(date_part), time_part


def jalali_year_range(jy: int) -> tuple[str, str]:
    """
    بازه تاریخ میلادی (from, to) معادل یک سال شمسی کامل — برای گزارش سالانه.
    پایان سال با «یک روز قبل از فروردین ۱ سال بعد» محاسبه می‌شود تا اسفند ۲۹/۳۰-روزه
    (سال کبیسه) به‌درستی و بدون نیاز به منطق جداگانه لحاظ شود.
    """
    from datetime import timedelta
    start = jdatetime.date(jy, 1, 1).togregorian()
    next_year_start = jdatetime.date(jy + 1, 1, 1).togregorian()
    end = next_year_start - timedelta(days=1)
    return start.isoformat(), end.isoformat()
