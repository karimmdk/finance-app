import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import run as run_module


def test_resource_dir_points_to_project_root_not_its_parent():
    """
    رگرسیون: نسخه اولیه _base_dir() از `.parent.parent` استفاده می‌کرد که یک پوشه بالاتر از
    ریشه واقعی پروژه می‌رفت (چون run.py خودش در ریشه است، نه در یک زیرپوشه مثل app/db.py).
    نتیجه: static/migrations با مسیر اشتباه جست‌وجو می‌شدند و فرانت‌اند 404 می‌داد.
    """
    resource_dir = run_module._resource_dir()
    assert (resource_dir / "app").is_dir()
    assert (resource_dir / "migrations").is_dir()
    assert (resource_dir / "static").exists()  # حتی اگر خالی باشد، پوشه باید وجود داشته باشد


def test_writable_dir_also_points_to_project_root_in_dev_mode():
    writable_dir = run_module._writable_dir()
    assert (writable_dir / "app").is_dir()
