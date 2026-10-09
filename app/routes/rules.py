import json
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_db
from app.schemas import RuleIn, RuleUpdate
from pydantic import BaseModel
from app.lib.rules_engine import load_active_rules, evaluate_rules, apply_rule_actions

router = APIRouter()


class RunAllIn(BaseModel):
    # True: دسته/شخصِ تعیین‌شده توسط قوانین، مقدار فعلی تراکنش را هم عوض می‌کند (بازمحاسبه کامل).
    # False: فقط جای خالی دسته/شخص پر می‌شود و برچسب‌ها اضافه می‌شوند.
    overwriteCategory: bool = True


def _txn_context(row) -> dict:
    return {
        "description": row["description"], "counterparty": row["counterparty"], "amount": row["amount"],
        "type": row["type"], "raw_transaction_type": row["raw_transaction_type"],
    }


@router.get("")
def list_rules(db: sqlite3.Connection = Depends(get_db)):
    rows = [dict(r) for r in db.execute("SELECT * FROM rules ORDER BY id DESC")]
    for r in rows:
        r["condition"] = json.loads(r["condition"])
        r["actions"] = json.loads(r["actions"])
    return rows


@router.post("", status_code=201)
def create_rule(body: RuleIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO rules (name, condition, actions, active, auto_apply) VALUES (?, ?, ?, ?, ?)",
        (body.name, json.dumps(body.condition), json.dumps(body.actions), int(body.active), int(body.autoApply)),
    )
    db.commit()
    return {"id": cur.lastrowid}


@router.put("/{rule_id}")
def update_rule(rule_id: int, body: RuleUpdate, db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "قانون یافت نشد")
    d = body.model_dump(exclude_unset=True)
    db.execute(
        "UPDATE rules SET name=?, condition=?, actions=?, active=?, auto_apply=? WHERE id=?",
        (
            d.get("name", existing["name"]),
            json.dumps(d["condition"]) if "condition" in d else existing["condition"],
            json.dumps(d["actions"]) if "actions" in d else existing["actions"],
            int(d["active"]) if "active" in d else existing["active"],
            int(d["autoApply"]) if "autoApply" in d else existing["auto_apply"],
            rule_id,
        ),
    )
    db.commit()
    return {"ok": True}


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
    db.commit()
    return {"ok": True}


@router.post("/run-on-uncategorized")
def run_on_uncategorized(db: sqlite3.Connection = Depends(get_db)):
    """
    نکته: قبلاً فقط تراکنش‌های بدون دسته‌بندی را می‌گرفت — با اضافه‌شدن قابلیت تگ به قوانین،
    یک قانون فقط-تگ باید روی تراکنش‌های بدون تگ هم اجرا شود حتی اگر از قبل دسته‌بندی دارند.
    همه قوانین منطبق ادغام می‌شوند (نه فقط اولین قانون).
    """
    pending = db.execute(
        """SELECT id, description, counterparty, amount, type, raw_transaction_type FROM transactions
           WHERE category_id IS NULL
              OR NOT EXISTS (SELECT 1 FROM transaction_tags WHERE transaction_id = transactions.id)"""
    ).fetchall()
    rules = load_active_rules(db)
    applied, suggested = [], []
    for txn in pending:
        result = evaluate_rules(rules, _txn_context(txn))
        if result["actions"]:
            apply_rule_actions(db, txn["id"], result["actions"], commit=False)
            applied.append({"transactionId": txn["id"], "ruleName": "، ".join(result["applied"])})
        if result["suggested"]:
            suggested.append({"transactionId": txn["id"], "ruleName": "، ".join(result["suggested"])})
    db.commit()
    return {"applied": applied, "suggested": suggested}


@router.post("/run-on-all")
def run_on_all(body: RunAllIn = RunAllIn(), db: sqlite3.Connection = Depends(get_db)):
    """
    اعمال مجدد همه قوانین فعال روی «همه» تراکنش‌ها (بدون توجه به این‌که دسته یا تگ دارند یا نه).
    مثل لحظه ایمپورت عمل می‌کند: تگ‌ها اضافه می‌شوند (هیچ تگی حذف نمی‌شود) و دسته/شخص طبق
    قوانین (قانون جدیدتر غالب است) تنظیم می‌شود. کل عملیات اتمیک است.
    خروجی: total = تعداد تراکنش‌های بررسی‌شده، matched = تعداد تراکنش‌هایی که حداقل یک قانون
    خودکار داشتند، changed = تعداد تراکنش‌هایی که واقعاً تغییر کردند، suggested = پیشنهادهای دستی.
    """
    rules = load_active_rules(db)
    rows = db.execute(
        "SELECT id, description, counterparty, amount, type, raw_transaction_type FROM transactions"
    ).fetchall()
    matched = changed = suggested = 0
    try:
        for txn in rows:
            result = evaluate_rules(rules, _txn_context(txn))
            if result["suggested"]:
                suggested += 1
            if not result["actions"]:
                continue
            matched += 1
            if apply_rule_actions(db, txn["id"], result["actions"],
                                   overwrite=body.overwriteCategory, commit=False):
                changed += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"total": len(rows), "matched": matched, "changed": changed, "suggested": suggested,
            "activeRules": len(rules)}
