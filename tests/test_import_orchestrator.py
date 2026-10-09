import pytest
from app.db import open_db
from app.importers.import_orchestrator import run_import, undo_import_batch
from app.lib.duplicate_detection import NormalizedTransaction


@pytest.fixture
def conn():
    c = open_db(":memory:")
    yield c
    c.close()


@pytest.fixture
def account_id(conn):
    cur = conn.execute("INSERT INTO accounts (name, type, initial_balance) VALUES ('حساب','bank',0)")
    conn.commit()
    return cur.lastrowid


def make_txn(account_id, **overrides):
    base = dict(
        account_id=account_id, transaction_date="2026-01-01", transaction_time="10:00:00",
        amount=100000, type="expense", description="test", document_number="DOC1",
        balance_after=900000, source_row_number=1,
    )
    base.update(overrides)
    return NormalizedTransaction(**base)


def test_imports_new_transactions(conn, account_id):
    summary = run_import(conn, account_id, "test.xlsx", "generic-bank-xlsx",
                          [make_txn(account_id), make_txn(account_id, document_number="DOC2", amount=50000)], [])
    assert summary["new_count"] == 2
    count = conn.execute("SELECT COUNT(*) as c FROM transactions").fetchone()["c"]
    assert count == 2


def test_skips_definite_duplicates_on_reimport(conn, account_id):
    run_import(conn, account_id, "a.xlsx", "generic-bank-xlsx", [make_txn(account_id)], [])
    second = run_import(conn, account_id, "b.xlsx", "generic-bank-xlsx", [make_txn(account_id)], [])
    assert second["definite_duplicate_count"] == 1
    assert second["new_count"] == 0
    count = conn.execute("SELECT COUNT(*) as c FROM transactions").fetchone()["c"]
    assert count == 1


def test_undo_import_batch_removes_transactions(conn, account_id):
    summary = run_import(conn, account_id, "test.xlsx", "generic-bank-xlsx",
                          [make_txn(account_id), make_txn(account_id, document_number="DOC2")], [])
    undo_import_batch(conn, summary["batch_id"])
    count = conn.execute("SELECT COUNT(*) as c FROM transactions").fetchone()["c"]
    assert count == 0
    status = conn.execute("SELECT status FROM import_batches WHERE id = ?", (summary["batch_id"],)).fetchone()
    assert status["status"] == "rolled_back"


def test_rolls_back_entire_import_on_error(conn, account_id):
    bad_txn = make_txn(99999)  # FK به حساب ناموجود
    with pytest.raises(Exception):
        run_import(conn, account_id, "bad.xlsx", "generic-bank-xlsx", [make_txn(account_id), bad_txn], [])
    count = conn.execute("SELECT COUNT(*) as c FROM transactions").fetchone()["c"]
    assert count == 0  # هیچ ردیفی، حتی ردیف معتبر اول، نباید باقی بماند


def test_description_parser_wired_into_import(conn, account_id):
    txn = make_txn(account_id, description="انتقال به آقای علی رضایی بانک ملت", document_number="DOC-X")
    run_import(conn, account_id, "test.xlsx", "generic-bank-xlsx", [txn], [])
    row = conn.execute("SELECT counterparty, bank_name FROM transactions WHERE document_number = 'DOC-X'").fetchone()
    assert row["counterparty"] == "علی رضایی"
    assert row["bank_name"] == "ملت"


def test_default_seeded_rules_auto_categorize_on_import(conn, account_id):
    """رگرسیون end-to-end: دسته‌بندی‌ها و قوانین پیش‌فرض (migration 0004/0005) واقعاً روی
    ایمپورت اعمال می‌شوند، نه فقط این‌که در دیتابیس وجود دارند."""
    txn = make_txn(account_id, description="خرید کالا از اینترنت", document_number="DOC-CAT",
                    raw_transaction_type="خرید اینترنتی")
    run_import(conn, account_id, "test.xlsx", "generic-bank-xlsx", [txn], [], apply_rules=True)
    row = conn.execute(
        "SELECT t.category_id, c.name FROM transactions t JOIN categories c ON c.id = t.category_id "
        "WHERE t.document_number = 'DOC-CAT'"
    ).fetchone()
    assert row["name"] == "خرید آنلاین"


def test_correction_rows_get_category_and_review_tag(conn, account_id):
    """رگرسیون: ردیف‌های «اصلاح سند» تا قبل از migration 0006 هیچ دسته‌بندی/تگ خودکاری نداشتند."""
    txn = make_txn(account_id, document_number="DOC-FIX", raw_transaction_type="اصلاح سند")
    run_import(conn, account_id, "test.xlsx", "generic-bank-xlsx", [txn], [], apply_rules=True)
    row = conn.execute(
        "SELECT t.id, c.name FROM transactions t JOIN categories c ON c.id = t.category_id WHERE t.document_number = 'DOC-FIX'"
    ).fetchone()
    assert row["name"] == "متفرقه"
    tags = [r["name"] for r in conn.execute(
        "SELECT tg.name FROM tags tg JOIN transaction_tags tt ON tt.tag_id = tg.id WHERE tt.transaction_id = ?", (row["id"],)
    )]
    assert "نیاز به بررسی" in tags
