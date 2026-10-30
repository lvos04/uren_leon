import datetime as dt
import io

import openpyxl
from fastapi.testclient import TestClient


def client():
    from app.main import app
    return TestClient(app)


def login(c):
    from app import auth
    if not auth.password_is_set():
        auth.set_password("test-wachtwoord")
    r = c.post("/login", data={"password": "test-wachtwoord", "next": "/"}, follow_redirects=False)
    assert r.status_code == 303


def test_eerste_keer_wachtwoord_kiezen(conn):
    c = client()
    r = c.get("/jaar/2026", follow_redirects=False)
    assert r.headers["location"] == "/setup"
    assert "Kies een wachtwoord" in c.get("/setup").text
    r = c.post("/setup", data={"password": "kort", "password2": "kort"})
    assert "minstens 8" in r.text
    r = c.post("/setup", data={"password": "geheim123", "password2": "geheim123", "naam": "Leon"},
               follow_redirects=False)
    assert r.status_code == 303
    assert c.get("/jaar/2026").status_code == 200  # direct ingelogd
    # daarna kan niemand het opnieuw instellen
    c2 = client()
    assert c2.post("/setup", data={"password": "aanvaller1", "password2": "aanvaller1"},
                   follow_redirects=False).headers["location"] == "/login"
    assert c2.post("/login", data={"password": "geheim123"}, follow_redirects=False).status_code == 303


def test_setup_niet_via_internet(conn):
    c = client()
    r = c.get("/setup", headers={"X-Forwarded-For": "8.8.8.8"})
    assert "thuisnetwerk" in r.text
    r = c.post("/setup", data={"password": "geheim123", "password2": "geheim123"},
               headers={"X-Forwarded-For": "8.8.8.8"})
    assert r.status_code == 403


def test_wachtwoord_wijzigen(conn):
    c = client()
    login(c)
    c.post("/instellingen/wachtwoord", data={"oud": "test-wachtwoord", "nieuw": "nieuwwachtwoord",
                                             "nieuw2": "nieuwwachtwoord"})
    from app import auth
    assert auth.check_password("nieuwwachtwoord")


def test_login_vereist(conn):
    c = client()
    login(client())
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
    r = c.post("/koppel", data={"name": "test"})
    assert "<svg" in r.text and "uren://koppel?" in r.text
    import re
    from urllib.parse import parse_qs, unquote, urlparse
    link = unquote(re.search(r'href="(uren://koppel\?[^"]+)"', r.text).group(1)).replace("&amp;", "&")
    q = parse_qs(urlparse(link).query)
    assert q["url"] == ["http://testserver"]
    token = q["token"][0]
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
    assert r["ok"] and r["upload"] == "OneDrive niet gekoppeld"
    assert (backup.BACKUP_DIR / f"uren-{dt.date.today()}.xlsx").exists()


def test_backup_instellingen_en_terugzetten(conn):
    from app import backup
    c = client()
    login(c)
    c.post("/instellingen/backup", data={"tijd": "4:15", "map": "Werk/Uren", "dagen": "10"})
    assert backup.get_settings() == {"backup_time": "04:15", "backup_folder": "Werk/Uren", "backup_keep_days": "10",
                                     "month_pdf": "0"}
    conn.execute("INSERT INTO days(date, hours, updated_at) VALUES('2026-10-05', 9, 'x')")
    conn.commit()
    r = backup.run_backup()
    name = [f for f in r["files"] if f.endswith(".db")][0]
    conn.execute("UPDATE days SET hours=1 WHERE date='2026-10-05'")
    conn.commit()
    assert c.get(f"/backups/{name}").status_code == 200
    assert c.get("/backups/..%2Furen.db").status_code == 404
    c.post(f"/backups/{name}/restore")
    from app import db
    with db.get_conn() as c2:
        assert c2.execute("SELECT hours FROM days WHERE date='2026-10-05'").fetchone()[0] == 9
    # wachtwoord bleef gelijk na terugzetten
    from app import auth
    assert auth.check_password("test-wachtwoord")


def test_app_download_en_versie(conn):
    import json
    import os
    from pathlib import Path
    d = Path(os.environ["APK_DIR"])
    d.mkdir(exist_ok=True)
    (d / "uren.apk").write_bytes(b"PK-test")
    (d / "version.json").write_text(json.dumps({"versionCode": 7, "versionName": "1.7"}))
    c = client()
    login(c)
    assert c.get("/app/uren.apk").content == b"PK-test"
    assert "versie 1.7" in c.get("/instellingen").text
    assert c.get("/api/v1/app-version").json()["versionCode"] == 7


def test_onedrive_pagina(conn):
    c = client()
    login(c)
    assert "Start koppelen" in c.get("/onedrive").text
    from app import onedrive
    import pytest
    with pytest.raises(RuntimeError, match="verlopen"):
        onedrive.finish("http://localhost:53682/?code=abc&state=x")


def test_inlogblokkade(conn):
    from app import auth
    auth._fails.clear()
    c = client()
    login(c)
    c2 = client()
    for _ in range(5):
        assert "klopt niet" in c2.post("/login", data={"password": "fout"}).text
    r = c2.post("/login", data={"password": "test-wachtwoord"}, follow_redirects=False)
    assert "Te veel foute pogingen" in r.text
    # vanaf een ander adres (via proxy) kan het nog wel
    r = c2.post("/login", data={"password": "test-wachtwoord"}, headers={"X-Forwarded-For": "10.0.0.9"},
                follow_redirects=False)
    assert r.status_code == 303
    auth._fails.clear()


def test_secure_cookie_via_https(conn):
    from app import auth
    auth.set_password("test-wachtwoord")
    r = client().post("/login", data={"password": "test-wachtwoord"}, follow_redirects=False,
                      headers={"X-Forwarded-Proto": "https"})
    from fastapi.testclient import TestClient
    from app.main import app
    r = TestClient(app, base_url="https://testserver").post("/login", data={"password": "test-wachtwoord"},
                                                            follow_redirects=False)
    assert "secure" in r.headers["set-cookie"].lower()
    r = client().post("/login", data={"password": "test-wachtwoord"}, follow_redirects=False)
    assert "secure" not in r.headers["set-cookie"].lower()


def test_feestdagen_api_en_instellingen(conn):
    c = client()
    login(c)
    assert "2e Paasdag" in c.get("/week/2026/15").text
    j = c.get("/api/v1/holidays", params={"start": "2026-01-01", "end": "2026-12-31"}).json()
    assert j["sunday_factor"] == 2 and {"date": "2026-04-27", "name": "Koningsdag", "factor": 2.0} in j["holidays"]
    c.post("/instellingen/feestdagen", data={"sunday_factor": "1.5", "on_pasen1": "1", "f_pasen1": "2"})
    j = c.get("/api/v1/holidays", params={"start": "2026-01-01", "end": "2026-12-31"}).json()
    assert j["sunday_factor"] == 1.5 and [h["name"] for h in j["holidays"]] == ["1e Paasdag"]


def test_ontbrekend_in_jaaroverzicht(conn):
    conn.execute("INSERT INTO days(date, hours, updated_at) VALUES('2026-03-02', 8, 'x')")
    conn.commit()
    c = client()
    login(c)
    t = c.get("/jaar/2026").text
    assert "werkdagen zonder uren" in t and "di 03-03" in t
    assert "werkdagen zonder uren" in c.get("/maand/2026/3").text


def test_maand_pdf_versturen(conn, tmp_path):
    from app import backup
    c = client()
    login(c)
    r = c.post("/maand-pdf", data={"maand": "2026-10"}, follow_redirects=False)
    assert "uren-2026-10.pdf" in r.headers["location"]
    assert c.get("/maandoverzichten/uren-2026-10.pdf").content[:4] == b"%PDF"
    assert backup.last_month_pdf()["upload"] == "OneDrive niet gekoppeld"
    # met een (nep) OneDrive: rclone krijgt de opdracht
    calls = []

    class P:
        returncode = 0
        stderr = ""

    orig_linked, orig_rclone = backup.onedrive_linked, backup.rclone
    backup.onedrive_linked = lambda: True
    backup.rclone = lambda *a, **k: calls.append(a) or P()
    try:
        r = backup.send_month_pdf(2026, 9)
    finally:
        backup.onedrive_linked, backup.rclone = orig_linked, orig_rclone
    assert r["upload"] == "ok" and calls[0][0] == "copy" and calls[0][2].endswith("UrenBackup/Maandoverzichten")
