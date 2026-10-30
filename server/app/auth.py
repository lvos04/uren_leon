"""Inloggen: wachtwoord voor de web-UI (APP_PASSWORD), Bearer-token voor de Android-app."""
import datetime as dt
import hashlib
import hmac
import os
import secrets
import time

from fastapi import HTTPException, Request

from .db import get_conn


class NeedLogin(Exception):
    pass


def app_password() -> str:
    pw = os.environ.get("APP_PASSWORD", "")
    if not pw:
        raise RuntimeError("Stel de omgevingsvariabele APP_PASSWORD in.")
    return pw


def check_password(given: str) -> bool:
    ok = hmac.compare_digest(given.encode(), app_password().encode())
    if not ok:
        time.sleep(1)  # brute force afremmen
    return ok


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_token(name: str) -> str:
    token = secrets.token_urlsafe(32)
    with get_conn() as conn:
        conn.execute("INSERT INTO tokens(name, token_hash, created_at) VALUES(?,?,?)",
                     (name, _hash(token), dt.datetime.now().isoformat(timespec="seconds")))
    return token


def token_valid(token: str) -> bool:
    with get_conn() as conn:
        return conn.execute("SELECT 1 FROM tokens WHERE token_hash=?", (_hash(token),)).fetchone() is not None


def is_logged_in(request: Request) -> bool:
    return bool(request.session.get("ok"))


def require_web(request: Request):
    if not is_logged_in(request):
        raise NeedLogin()


def require_api(request: Request):
    """API: Bearer-token, of ingelogde browser-sessie."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer ") and token_valid(auth[7:].strip()):
        return
    if is_logged_in(request):
        return
    time.sleep(0.5)
    raise HTTPException(status_code=401, detail="Ongeldig token")
