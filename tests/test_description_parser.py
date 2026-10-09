from app.lib.description_parser import parse_transaction_description


def test_no_structured_data_real_sample_case():
    result = parse_transaction_description("خرید کالا و خدمات از اینترنت")
    assert result["counterparty"] is None
    assert result["card_number"] is None
    assert result["iban"] is None
    assert result["bank_name"] is None
    assert result["reason"] == "خرید کالا و خدمات از اینترنت"


def test_extracts_masked_card_number():
    result = parse_transaction_description("انتقال به کارت 6274-****-****-1234 بابت خرید")
    assert result["card_number"] == "6274********1234"


def test_extracts_full_card_number():
    result = parse_transaction_description("واریز به کارت 6037991234567890")
    assert result["card_number"] == "6037991234567890"


def test_extracts_iban_standard_format():
    result = parse_transaction_description("انتقال به شبا IR820540102680020817909002")
    assert result["iban"] == "IR820540102680020817909002"


def test_extracts_iban_after_persian_label():
    result = parse_transaction_description("شبا: 820540102680020817909002")
    assert result["iban"] == "IR820540102680020817909002"


def test_extracts_known_bank_name():
    result = parse_transaction_description("انتقال از سپرده بلو")
    assert result["bank_name"] == "بلو"


def test_extracts_counterparty_after_keyword():
    result = parse_transaction_description("انتقال به آقای علی رضایی شماره کارت 6274123456781234")
    assert result["counterparty"] == "علی رضایی"


def test_counterparty_does_not_swallow_bank_name():
    result = parse_transaction_description("انتقال به آقای علی رضایی بانک ملت")
    assert result["counterparty"] == "علی رضایی"
    assert result["bank_name"] == "ملت"


def test_handles_none_description():
    result = parse_transaction_description(None)
    assert result == {"counterparty": None, "card_number": None, "iban": None, "bank_name": None, "reason": None}


def test_no_invented_counterparty_without_keyword():
    result = parse_transaction_description("برداشت بابت کارمزد")
    assert result["counterparty"] is None


def test_real_world_blue_bank_deposit_transfer_format():
    """
    رگرسیون: نمونه واقعی که کاربر گزارش داد. دو باگ واقعی اینجا پیدا شد:
    1. "دی" (بانک دی) به‌اشتباه به‌عنوان substring داخل "احمدی" (نام‌خانوادگی) پیدا می‌شد چون
       تطبیق بدون مرز کلمه (word boundary) بود.
    2. خط تیره جداکننده ("- شماره سند") باعث می‌شد lookahead استخراج نام طرف‌حساب fail کند.
    """
    text = "انتقال از سپرده بلو - شماره سپرده: 611828005275774801 بنام: محسن احمدی - شماره سند: 14053105563436"
    result = parse_transaction_description(text)
    assert result["bank_name"] == "بلو"  # نه "دی"
    assert result["counterparty"] == "محسن احمدی"
    assert result["card_number"] == "611828005275774801"  # از "شماره سپرده" چون شماره کارت واقعی نبود


def test_bank_name_matching_respects_word_boundaries():
    """رگرسیون مستقیم: "دی" هرگز نباید داخل کلماتی مثل "احمدی"/"محمدی" پیدا شود."""
    result = parse_transaction_description("پرداخت به آقای محمدی بابت خرید")
    assert result["bank_name"] is None


def test_labeled_deposit_account_number_extracted_as_card_number():
    result = parse_transaction_description("شماره سپرده: 123456789012345678 بنام تست")
    assert result["card_number"] == "123456789012345678"

