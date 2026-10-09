from app.lib.anomaly_detection import compute_category_stats, is_anomalous_amount


def test_computes_average_and_stddev():
    stats = compute_category_stats([100, 100, 100, 100])
    assert stats["avg"] == 100
    assert stats["stddev"] == 0
    assert stats["count"] == 4


def test_empty_input_returns_zeroed_stats():
    assert compute_category_stats([]) == {"avg": 0, "stddev": 0, "count": 0}


def test_flags_amount_far_above_average():
    stats = compute_category_stats([100000, 110000, 90000, 105000, 95000])
    assert is_anomalous_amount(1000000, stats) is True


def test_does_not_flag_normal_amount():
    stats = compute_category_stats([100000, 110000, 90000, 105000, 95000])
    assert is_anomalous_amount(102000, stats) is False


def test_does_not_flag_with_small_sample():
    stats = compute_category_stats([100000, 200000])
    assert is_anomalous_amount(5000000, stats) is False


def test_no_false_positive_low_variance_modest_increase():
    stats = compute_category_stats([500000, 500000, 500000, 500000])
    assert is_anomalous_amount(600000, stats) is False


def test_flags_large_jump_even_low_variance():
    stats = compute_category_stats([500000, 500000, 500000, 500000])
    assert is_anomalous_amount(2000000, stats) is True
