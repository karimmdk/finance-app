from app.lib.duplicate_detection import NormalizedTransaction, detect_duplicate

BASE_INCOMING = NormalizedTransaction(
    account_id=1, transaction_date="2026-06-01", transaction_time="12:00:00",
    amount=100000, type="expense", description="خرید از فروشگاه X",
    document_number="14052732973246", balance_after=500000, source_row_number=1,
)

EXISTING_SAMPLE = [{
    "id": 10, "account_id": 1, "transaction_date": "2026-06-01", "amount": 100000,
    "type": "expense", "document_number": "14052732973246", "description": "خرید از فروشگاه X",
}]


def test_definite_duplicate_on_document_number():
    result = detect_duplicate(BASE_INCOMING, EXISTING_SAMPLE)
    assert result["status"] == "definite_duplicate"


def test_definite_duplicate_on_date_amount_type_without_doc_number():
    import dataclasses
    incoming = dataclasses.replace(BASE_INCOMING, document_number=None)
    existing = [{**EXISTING_SAMPLE[0], "document_number": None}]
    result = detect_duplicate(incoming, existing)
    assert result["status"] == "definite_duplicate"


def test_probable_duplicate_one_day_off():
    import dataclasses
    incoming = dataclasses.replace(BASE_INCOMING, document_number="OTHER_DOC", transaction_date="2026-06-02")
    result = detect_duplicate(incoming, EXISTING_SAMPLE)
    assert result["status"] == "probable_duplicate"


def test_new_when_nothing_matches():
    import dataclasses
    incoming = dataclasses.replace(BASE_INCOMING, document_number="UNIQUE", transaction_date="2026-09-01", amount=999999)
    result = detect_duplicate(incoming, EXISTING_SAMPLE)
    assert result["status"] == "new"


def test_no_cross_account_match():
    import dataclasses
    incoming = dataclasses.replace(BASE_INCOMING, account_id=2)
    result = detect_duplicate(incoming, EXISTING_SAMPLE)
    assert result["status"] == "new"


def test_no_false_match_beyond_one_day():
    import dataclasses
    incoming = dataclasses.replace(BASE_INCOMING, document_number="OTHER", transaction_date="2026-06-10")
    result = detect_duplicate(incoming, EXISTING_SAMPLE)
    assert result["status"] == "new"


# ---------- رگرسیون: داده واقعی صورتحساب (چند ردیف با شماره سند مشترک / مبلغ یکسان در یک روز) ----------
def test_same_document_number_but_different_amount_is_not_duplicate():
    # سند ۱۴۰۵۴۸۶۸۶۷۲۷۷۳ واقعی: ۳ ردیف (تمبر ۷۵۰هزار، بازپرداخت ۲۰م، تسهیلات ۴۰۰م) با یک شماره سند
    import dataclasses
    existing = [{**EXISTING_SAMPLE[0], "amount": 750000}]
    incoming = dataclasses.replace(BASE_INCOMING, amount=20000000)
    assert detect_duplicate(incoming, existing)["status"] == "new"


def test_same_day_amount_type_but_different_document_numbers_is_not_definite_duplicate():
    # دو واریز ۱۰۰ میلیونی واقعی در یک روز با شماره سند متفاوت
    import dataclasses
    existing = [{**EXISTING_SAMPLE[0], "document_number": "14054868222067"}]
    incoming = dataclasses.replace(BASE_INCOMING, document_number="14054868378051")
    assert detect_duplicate(incoming, existing)["status"] != "definite_duplicate"


def test_same_document_amount_type_is_still_definite():
    assert detect_duplicate(BASE_INCOMING, EXISTING_SAMPLE)["status"] == "definite_duplicate"
