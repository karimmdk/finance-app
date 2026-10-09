"""Import کامل تراکنشی — معادل src/importers/import-orchestrator.ts."""
import sqlite3
from app.db import transaction as db_transaction
from app.lib.duplicate_detection import detect_duplicate, NormalizedTransaction
from app.lib.rules_engine import load_active_rules, evaluate_rules, apply_rule_actions
from app.lib.description_parser import parse_transaction_description


def run_import(conn: sqlite3.Connection, account_id: int, file_name: str, adapter: str,
                transactions: list[NormalizedTransaction], issues: list[dict],
                decisions: dict[int, str] | None = None, apply_rules: bool = False) -> dict:
    existing = [
        dict(row) for row in conn.execute(
            """SELECT id, account_id, transaction_date, amount, type, document_number, description
               FROM transactions WHERE account_id = ?""",
            (account_id,),
        )
    ]

    rules = load_active_rules(conn) if apply_rules else []
    rules_applied_count = 0

    with db_transaction(conn):
        cur = conn.execute(
            "INSERT INTO import_batches (account_id, file_name, adapter, imported_count, duplicate_count, status) "
            "VALUES (?, ?, ?, 0, 0, 'completed')",
            (account_id, file_name, adapter),
        )
        batch_id = cur.lastrowid

        new_count = definite_duplicate_count = probable_duplicate_count = adjustment_count = 0
        total_deposit = total_withdrawal = 0

        for idx, incoming in enumerate(transactions):
            if incoming.type == "adjustment":
                adjustment_count += 1
                dup_result = {"status": "new"}
            else:
                dup_result = detect_duplicate(incoming, existing)

            decision = (decisions or {}).get(idx, "ignore" if dup_result["status"] == "definite_duplicate" else "import")

            if dup_result["status"] == "definite_duplicate":
                definite_duplicate_count += 1
            if dup_result["status"] == "probable_duplicate":
                probable_duplicate_count += 1

            if incoming.type in ("income", "adjustment"):
                total_deposit += max(incoming.amount, 0)
            if incoming.type == "expense":
                total_withdrawal += incoming.amount

            if decision != "import":
                continue

            parsed = parse_transaction_description(incoming.description)

            cur = conn.execute(
                """INSERT INTO transactions
                   (account_id, transaction_date, transaction_time, amount, type, balance_after, description,
                    document_number, source, import_batch_id, source_row_number,
                    counterparty, card_number, iban, bank_name, reason, raw_transaction_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'import', ?, ?, ?, ?, ?, ?, ?, ?)""",
                (incoming.account_id, incoming.transaction_date, incoming.transaction_time, incoming.amount,
                 incoming.type, incoming.balance_after, incoming.description, incoming.document_number,
                 batch_id, incoming.source_row_number,
                 parsed["counterparty"], parsed["card_number"], parsed["iban"], parsed["bank_name"], parsed["reason"],
                 incoming.raw_transaction_type),
            )
            new_count += 1

            if apply_rules and rules:
                # همه قوانین منطبق ادغام می‌شوند (نه فقط اولین)؛ commit=False تا کل import اتمیک بماند
                result = evaluate_rules(rules, {
                    "description": incoming.description,
                    "counterparty": parsed["counterparty"],
                    "amount": incoming.amount,
                    "type": incoming.type,
                    "raw_transaction_type": incoming.raw_transaction_type,
                })
                if result["actions"] and apply_rule_actions(conn, cur.lastrowid, result["actions"], commit=False):
                    rules_applied_count += 1

        conn.execute(
            "UPDATE import_batches SET imported_count = ?, duplicate_count = ? WHERE id = ?",
            (new_count, definite_duplicate_count + probable_duplicate_count, batch_id),
        )

    return {
        "batch_id": batch_id,
        "total": len(transactions),
        "new_count": new_count,
        "definite_duplicate_count": definite_duplicate_count,
        "probable_duplicate_count": probable_duplicate_count,
        "adjustment_count": adjustment_count,
        "rules_applied_count": rules_applied_count,
        # نسخه camelCase برای فرانت‌اند (صفحه ایمپورت newCount/definiteDuplicateCount را می‌خواند)
        "newCount": new_count,
        "definiteDuplicateCount": definite_duplicate_count,
        "probableDuplicateCount": probable_duplicate_count,
        "rulesApplied": rules_applied_count,
        "total_deposit": total_deposit,
        "total_withdrawal": total_withdrawal,
        "issues": issues,
    }


def undo_import_batch(conn: sqlite3.Connection, batch_id: int) -> None:
    with db_transaction(conn):
        conn.execute("DELETE FROM transactions WHERE import_batch_id = ?", (batch_id,))
        conn.execute("UPDATE import_batches SET status = 'rolled_back' WHERE id = ?", (batch_id,))
