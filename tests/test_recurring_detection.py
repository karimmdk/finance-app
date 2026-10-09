from app.lib.recurring_detection import detect_recurring_series


def txn(date, **overrides):
    base = {"account_id": 1, "type": "expense", "amount": 500000, "description": "اشتراک نتفلیکس", "transaction_date": date}
    base.update(overrides)
    return base


def test_detects_monthly_subscription():
    txns = [txn("2026-01-15"), txn("2026-02-14"), txn("2026-03-16")]
    result = detect_recurring_series(txns, "2026-03-20")
    assert len(result) == 1
    assert result[0]["occurrence_count"] == 3
    assert result[0]["next_expected_date"].startswith("2026-04-1")


def test_days_until_next_negative_when_overdue():
    txns = [txn("2026-01-01"), txn("2026-02-01")]
    result = detect_recurring_series(txns, "2026-03-10")
    assert result[0]["days_until_next"] < 0


def test_single_occurrence_not_flagged():
    result = detect_recurring_series([txn("2026-01-15")], "2026-02-01")
    assert result == []


def test_irregular_coincidental_amount_not_flagged():
    txns = [txn("2026-01-01"), txn("2026-01-05"), txn("2026-06-20")]
    result = detect_recurring_series(txns, "2026-07-01")
    assert result == []


def test_different_amounts_kept_separate():
    txns = [
        txn("2026-01-15", amount=500000),
        txn("2026-02-14", amount=500000),
        txn("2026-01-20", amount=200000, description="اشتراک اسپاتیفای"),
        txn("2026-02-19", amount=200000, description="اشتراک اسپاتیفای"),
    ]
    result = detect_recurring_series(txns, "2026-03-01")
    assert len(result) == 2


def test_ignores_transfer_and_adjustment():
    txns = [txn("2026-01-15", type="transfer"), txn("2026-02-14", type="transfer")]
    result = detect_recurring_series(txns, "2026-03-01")
    assert result == []


def test_sorted_by_soonest_due_date():
    txns = [
        txn("2026-01-01", amount=100000, description="A"),
        txn("2026-02-01", amount=100000, description="A"),  # 31-day interval
        txn("2026-01-01", amount=200000, description="B"),
        txn("2026-01-28", amount=200000, description="B"),  # 27-day interval, sooner
    ]
    result = detect_recurring_series(txns, "2026-02-01")
    assert result[0]["description"] == "B"
