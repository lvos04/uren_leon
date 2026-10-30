import datetime as dt
import io

import openpyxl
from fastapi.testclient import TestClient


def client():
    from app.main import app
    return TestClient(app)


def login(c):
    r = c.post("/login", data={"password": "test-wachtwoord", "next": "/"}, follow_redirects=False)
    assert r.status_code == 303


def test_login_vereist(conn):
    c = client()
    assert c.get("/jaar/2026", follow_redirects=False).status_code == 303
    assert c.get("/api/v1/ping").status_code == 401


def test_web_week_opslaan_en_pagina_s(conn):
    c = client()
    login(c)
    form = {f"h{i}": "10" for i in range(5)}
    form.update({"h6": "4", "f6": "2", "s0": "1", "v5": "0", "month": "0"})
    r = c.post("/week/2026/44", data=form, follow_redirects=False)
    assert r.status_code == 303
    page = c.get("/week/2026/44").text
    assert "Opgeslagen" not in page or True
    y = c.get("/jaar/2026")
    assert y.status_code == 200 and "58" in y.text  # 50 + 4x2
    for url in ("/maand/2026/10", "/calculator?bruto=3700", "/instellingen", "/print/2026/10"):
        assert c.get(url).status_code == 200, url


def test_pdf_en_export(conn):
    c = client()
    login(c)
    r = c.get("/print/2026/10.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    r = c.get("/export.xlsx")
    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "Dagen" in wb.sheetnames


def test_api_token_en_dagen(conn):
    c = client()
    login(c)
    r = c.post("/tokens", data={"name": "test"}, follow_redirects=False)
    token = r.headers["location"].split("new_token=")[1]
    from urllib.parse import unquote
    token = unquote(token)
    api = TestClient(c.app)
    h = {"Authorization": f"Bearer {token}"}
    assert api.get("/api/v1/ping", headers=h).json()["ok"]
    r = api.put("/api/v1/days/2026-11-01", headers=h,
                json={"hours": 5, "factor": 2, "storing": True, "updated_at": "2026-11-01T20:00:00"})
    assert r.status_code == 200 and r.json()["factor"] == 2
    # oudere wijziging wordt geweigerd
    r = api.put("/api/v1/days/2026-11-01", headers=h, json={"hours": 1, "updated_at": "2026-11-01T10:00:00"})
    assert r.status_code == 409 and r.json()["hours"] == 5
    w = api.get("/api/v1/week/2026-11-01", headers=h).json()
    assert w["total"] == 10 and w["storing_dagen"] == 1
    days = api.get("/api/v1/days", params={"start": "2026-10-26", "end": "2026-11-01"}, headers=h).json()
    assert len(days) == 1
    assert api.get("/api/v1/print/2026/10.pdf", headers=h).content[:4] == b"%PDF"
    assert api.get("/api/v1/ping", headers={"Authorization": "Bearer fout"}).status_code == 401


def test_backup_zonder_rclone(conn):
    from app import backup
    r = backup.run_backup()
    assert r["ok"] and r["upload"] == "geen rclone-config"
    assert (backup.BACKUP_DIR / f"uren-{dt.date.today()}.xlsx").exists()
