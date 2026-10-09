import json
import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from app.deps import get_db
from app.schemas import SavedFilterIn

router = APIRouter()


@router.get("")
def list_saved_filters(db: sqlite3.Connection = Depends(get_db)):
    rows = [dict(r) for r in db.execute("SELECT * FROM saved_filters ORDER BY name")]
    for r in rows:
        r["filters"] = json.loads(r["filters"])
    return rows


@router.post("", status_code=201)
def create_saved_filter(body: SavedFilterIn, db: sqlite3.Connection = Depends(get_db)):
    try:
        cur = db.execute("INSERT INTO saved_filters (name, filters) VALUES (?, ?)", (body.name, json.dumps(body.filters)))
        db.commit()
        return {"id": cur.lastrowid}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "پیش‌نویسی با این نام از قبل وجود دارد")


@router.delete("/{filter_id}")
def delete_saved_filter(filter_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("DELETE FROM saved_filters WHERE id = ?", (filter_id,))
    db.commit()
    return {"ok": True}
