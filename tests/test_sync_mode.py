"""حالت سینک: journal_mode=DELETE (بدون -wal)، sync_dir.txt در دسکتاپ، و نقطه ورود اندروید."""
import importlib
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_journal_mode_delete_leaves_single_file(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCE_JOURNAL_MODE", "DELETE")
    from app.db import open_db
    db = open_db(str(tmp_path / "finance.db"))
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    db.commit()
    db.close()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["finance.db"]


def test_default_journal_mode_is_still_wal(tmp_path, monkeypatch):
    monkeypatch.delenv("FINANCE_JOURNAL_MODE", raising=False)
    from app.db import open_db
    db = open_db(str(tmp_path / "finance.db"))
    assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    db.close()


def test_android_main_migrates_legacy_restores_and_flushes(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "android" / "app" / "src" / "main" / "python"))
    import android_main
    importlib.reload(android_main)

    files, shared = tmp_path / "files", tmp_path / "shared" / "FinanceApp"
    private = files / "data"
    private.mkdir(parents=True)
    # دیتابیس قدیمی در حافظه خصوصی
    old = sqlite3.connect(str(private / "finance.db"))
    old.execute("CREATE TABLE legacy_marker (v TEXT)")
    old.execute("INSERT INTO legacy_marker VALUES ('kept')")
    old.commit(); old.close()

    port, token, used, warning = android_main.start(
        str(files), str(ROOT), str(shared), preferred_port=0)
    assert used == str(shared) and warning == ""
    assert (shared / "finance.db").exists()
    assert android_main.flush() is True
    assert sorted(p.name for p in shared.iterdir() if p.is_file()) == ["finance.db"]
    chk = sqlite3.connect(str(shared / "finance.db"))
    assert chk.execute("SELECT v FROM legacy_marker").fetchone()[0] == "kept"
    chk.close()


def test_desktop_sync_dir_txt(tmp_path):
    sync = tmp_path / "MEGA" / "finance"
    cfg = ROOT / "sync_dir.txt"
    cfg.write_text(f'"{sync}"\n', encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("FINANCE_")}
    env["PORT"] = "47999"
    proc = subprocess.Popen([sys.executable, str(ROOT / "run.py")], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen("http://127.0.0.1:47999/api/health"); break
            except Exception:
                time.sleep(0.25)
        assert (sync / "finance.db").exists()
        assert not (sync / "finance.db-wal").exists()
    finally:
        proc.terminate(); proc.wait(timeout=10)
        cfg.unlink(missing_ok=True)
