import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp()
os.environ["DATA_DIR"] = _tmp
os.environ.pop("APP_PASSWORD", None)
os.environ["APK_DIR"] = str(Path(_tmp) / "apk")
os.environ["DISABLE_SCHEDULER"] = "1"
os.environ["RCLONE_CONFIG"] = str(Path(_tmp) / "geen.conf")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def conn():
    from app import db
    db.init_db()
    c = db.connect()
    for t in ("days", "weeks", "months", "years", "payouts", "tokens", "meta"):
        c.execute(f"DELETE FROM {t}")
    c.commit()
    yield c
    c.commit()
    c.close()
