"""Inloggen: wachtwoord voor de web-UI (ingesteld bij eerste gebruik), Bearer-token voor de Android-app."""
import datetime as dt
import hashlib
import hmac
import ipaddress
import os
import secrets
import time

from fastapi import HTTPException, Request

from . import db
from .db import get_conn


class NeedLogin(Exception):
    pass


class NeedSetup(Exception):
    pass


# ---------------------------------------------------------------- wachtwoord
def _pbkdf2(password: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 300_000).hex()


def password_is_set() -> bool:
    with get_conn() as conn:
        return bool(db.get_meta(conn, "password_hash"))


def set_password(password: str) -> None:
    salt = secrets.token_bytes(16)
    with get_conn() as conn:
        db.set_meta(conn, "password_hash", f"{salt.hex()}${_pbkdf2(password, salt)}")


def check_password(given: str) -> bool:
    with get_conn() as conn:
        stored = db.get_meta(conn, "password_hash")
    ok = False
    if stored:
        salt_hex, h = stored.split("$", 1)
        ok = hmac.compare_digest(_pbkdf2(given, bytes.fromhex(salt_hex)), h)
    # noodsleutel: APP_PASSWORD (optioneel, bv. als je het wachtwoord kwijt bent)
    env = os.environ.get("APP_PASSWORD", "")
    if not ok and env:
        ok = hmac.compare_digest(given.encode(), env.encode())
    if not ok:
        time.sleep(1)  # brute force afremmen
    return ok


def is_private_client(request: Request) -> bool:
    """Eerste keer instellen mag alleen vanuit het eigen netwerk (niet via internet)."""
    hosts = [request.client.host if request.client else ""]
    hosts += [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    try:
        return all(ipaddress.ip_address(h).is_private or ipaddress.ip_address(h).is_loopback for h in hosts if h)
    except ValueError:
        return hosts == ["testclient"]


# ---------------------------------------------------------------- tokens
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


# ---------------------------------------------------------------- dependencies
def is_logged_in(request: Request) -> bool:
    return bool(request.session.get("ok"))


def require_web(request: Request):
    if not password_is_set():
        raise NeedSetup()
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
