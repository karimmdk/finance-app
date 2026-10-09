import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_db
from app.schemas import PersonIn, CategoryIn, TagIn
from app.lib.debt import get_person_net_position

people_router = APIRouter()
categories_router = APIRouter()
tags_router = APIRouter()


@people_router.get("")
def list_people(db: sqlite3.Connection = Depends(get_db)):
    people = [dict(r) for r in db.execute("SELECT * FROM people ORDER BY name")]
    for p in people:
        p["position"] = get_person_net_position(db, p["id"])
    return people


@people_router.get("/{person_id}")
def get_person(person_id: int, db: sqlite3.Connection = Depends(get_db)):
    row = db.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    if not row:
        raise HTTPException(404, "شخص یافت نشد")
    person = dict(row)
    person["position"] = get_person_net_position(db, person_id)
    return person


@people_router.post("", status_code=201)
def create_person(body: PersonIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO people (name, phone, description, account_number, notes) VALUES (?, ?, ?, ?, ?)",
        (body.name, body.phone, body.description, body.accountNumber, body.notes),
    )
    db.commit()
    return {"id": cur.lastrowid}


@people_router.put("/{person_id}")
def update_person(person_id: int, body: PersonIn, db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "شخص یافت نشد")
    db.execute(
        "UPDATE people SET name=?, phone=?, description=?, account_number=?, notes=? WHERE id=?",
        (body.name, body.phone, body.description, body.accountNumber, body.notes, person_id),
    )
    db.commit()
    return {"ok": True}


@people_router.delete("/{person_id}")
def delete_person(person_id: int, db: sqlite3.Connection = Depends(get_db)):
    debt_count = db.execute("SELECT COUNT(*) as c FROM debts WHERE person_id = ?", (person_id,)).fetchone()["c"]
    if debt_count > 0:
        raise HTTPException(400, "این شخص دارای بدهی/طلب ثبت‌شده است و قابل حذف نیست")
    db.execute("DELETE FROM people WHERE id = ?", (person_id,))
    db.commit()
    return {"ok": True}


@categories_router.get("")
def list_categories(db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute("SELECT * FROM categories ORDER BY parent_id IS NOT NULL, name")]


@categories_router.post("", status_code=201)
def create_category(body: CategoryIn, db: sqlite3.Connection = Depends(get_db)):
    cur = db.execute(
        "INSERT INTO categories (name, parent_id, icon, color) VALUES (?, ?, ?, ?)",
        (body.name, body.parentId, body.icon, body.color),
    )
    db.commit()
    return {"id": cur.lastrowid}


@categories_router.put("/{category_id}")
def update_category(category_id: int, body: CategoryIn, db: sqlite3.Connection = Depends(get_db)):
    existing = db.execute("SELECT * FROM categories WHERE id = ?", (category_id,)).fetchone()
    if not existing:
        raise HTTPException(404, "دسته‌بندی یافت نشد")
    db.execute(
        "UPDATE categories SET name=?, parent_id=?, icon=?, color=? WHERE id=?",
        (body.name, body.parentId, body.icon, body.color, category_id),
    )
    db.commit()
    return {"ok": True}


@categories_router.delete("/{category_id}")
def delete_category(category_id: int, db: sqlite3.Connection = Depends(get_db)):
    in_use = db.execute("SELECT COUNT(*) as c FROM transactions WHERE category_id = ?", (category_id,)).fetchone()["c"]
    if in_use > 0:
        raise HTTPException(400, "این دسته‌بندی در تراکنش‌ها استفاده شده و قابل حذف نیست")
    db.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    db.commit()
    return {"ok": True}


@tags_router.get("")
def list_tags(db: sqlite3.Connection = Depends(get_db)):
    return [dict(r) for r in db.execute("SELECT * FROM tags ORDER BY name")]


@tags_router.post("", status_code=201)
def create_tag(body: TagIn, db: sqlite3.Connection = Depends(get_db)):
    try:
        cur = db.execute("INSERT INTO tags (name, color) VALUES (?, ?)", (body.name, body.color))
        db.commit()
        return {"id": cur.lastrowid}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "این تگ از قبل وجود دارد")


@tags_router.delete("/{tag_id}")
def delete_tag(tag_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM transaction_tags WHERE tag_id = ?", (tag_id,))
    db.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
    db.commit()
    return {"ok": True}
