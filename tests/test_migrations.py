import tempfile
import os
from app.db import open_db


def test_repeated_opens_dont_crash_on_alter_table():
    """رگرسیون: نسخه اولیه هر migration را هر بار دوباره اجرا می‌کرد؛ ALTER TABLE در اجرای دوم کرش می‌کرد."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        conn1 = open_db(path)
        conn1.close()
        conn2 = open_db(path)  # قبل از fix اینجا با "duplicate column" خطا می‌داد
        conn2.close()
        conn3 = open_db(path)
        columns = [r["name"] for r in conn3.execute("PRAGMA table_info(transactions)")]
        assert "card_number" in columns
        assert "iban" in columns
        assert "bank_name" in columns
        assert "reason" in columns
        conn3.close()
    finally:
        for suffix in ["", "-wal", "-shm", "-journal"]:
            p = path + suffix
            if os.path.exists(p):
                os.remove(p)


def test_migrations_recorded_and_not_rerun():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)
    try:
        conn = open_db(path)
        applied = [r["filename"] for r in conn.execute("SELECT filename FROM schema_migrations ORDER BY filename")]
        assert applied == [
            "0000_init.sql", "0001_add_extracted_fields.sql", "0002_attachments_and_saved_filters.sql",
            "0003_add_raw_transaction_type.sql", "0004_seed_default_categories.sql", "0005_seed_default_rules.sql",
            "0006_correction_rule_and_review_tag.sql", "0007_exclude_from_analysis.sql",
        ]
        conn.close()
    finally:
        for suffix in ["", "-wal", "-shm", "-journal"]:
            p = path + suffix
            if os.path.exists(p):
                os.remove(p)
