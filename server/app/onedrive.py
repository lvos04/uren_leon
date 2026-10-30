"""OneDrive koppelen vanuit de web-app, zonder rclone op een pc.

Werking:
1. De server start `rclone authorize onedrive` (luistert in de container op 127.0.0.1:53682).
2. De server vraagt rclone om de Microsoft-inloglink en toont die als knop.
3. Na inloggen stuurt Microsoft de browser naar http://localhost:53682/?code=... . Die pagina laadt niet
   (het is je eigen telefoon/pc), maar het adres bevat de code. Dat adres plak je in de web-app.
4. De server geeft het adres door aan de wachtende rclone, die de code omwisselt voor een token.
5. De server zoekt de juiste OneDrive op en schrijft /data/rclone/rclone.conf.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from . import backup

AUTH_PORT = 53682
_lock = threading.Lock()
_proc: subprocess.Popen | None = None
_output: list[str] = []
_started = 0.0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def _reader(proc):
    for line in proc.stdout:
        _output.append(line)


def _stop():
    global _proc
    if _proc and _proc.poll() is None:
        _proc.kill()
    _proc = None


def start() -> str:
    """Start een nieuwe koppeling en geef de Microsoft-inloglink terug."""
    global _proc, _started
    with _lock:
        _stop()
        _output.clear()
        _proc = subprocess.Popen(
            ["rclone", "authorize", "onedrive", "--auth-no-open-browser", "--config", "/dev/null"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        _started = time.time()
        threading.Thread(target=_reader, args=(_proc,), daemon=True).start()
        local = None
        for _ in range(100):
            m = re.search(r"(http://127\.0\.0\.1:%d/auth\?state=[\w-]+)" % AUTH_PORT, "".join(_output))
            if m:
                local = m.group(1)
                break
            if _proc.poll() is not None:
                break
            time.sleep(0.1)
        if not local:
            _stop()
            raise RuntimeError("rclone kon de koppeling niet starten: " + "".join(_output)[-300:])
        # rclone stuurt door naar Microsoft; die doorverwijzing vangen we op
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            opener.open(local, timeout=10)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307) and e.headers.get("Location"):
                return e.headers["Location"]
            raise RuntimeError(f"Onverwacht antwoord van rclone ({e.code})")
        raise RuntimeError("Geen inloglink ontvangen van rclone")


def finish(pasted_url: str) -> dict:
    """Verwerk het geplakte localhost-adres en sla de koppeling op."""
    with _lock:
        if not _proc or _proc.poll() is not None or time.time() - _started > 20 * 60:
            raise RuntimeError("De koppeling is verlopen. Klik opnieuw op 'Inloggen bij Microsoft'.")
        q = urllib.parse.urlparse(pasted_url.strip()).query
        params = urllib.parse.parse_qs(q)
        if "error" in params:
            raise RuntimeError("Microsoft gaf een fout: " + params.get("error_description", params["error"])[0])
        if "code" not in params or "state" not in params:
            raise RuntimeError("Dit adres bevat geen code. Plak het hele adres uit de adresbalk (begint met http://localhost:53682/?code=).")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{AUTH_PORT}/?{q}", timeout=30).read()
        except urllib.error.HTTPError:
            pass
        for _ in range(300):
            text = "".join(_output)
            m = re.search(r"--->\s*(\{.*?\})\s*<---", text, re.S)
            if m:
                break
            if _proc.poll() is not None and "--->" not in text:
                break
            time.sleep(0.1)
        else:
            m = None
        _stop()
    if not m:
        raise RuntimeError("Inloggen mislukt: " + "".join(_output)[-300:].strip())
    token = json.loads(m.group(1))
    drive = _get_drive(token["access_token"])
    _write_config(token, drive["id"], drive.get("driveType", "personal"))
    return drive


def _get_drive(access_token: str) -> dict:
    req = urllib.request.Request("https://graph.microsoft.com/v1.0/me/drive",
                                 headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _write_config(token: dict, drive_id: str, drive_type: str) -> None:
    backup.RCLONE_CONF.parent.mkdir(parents=True, exist_ok=True)
    backup.RCLONE_CONF.write_text(
        f"[{backup.REMOTE_NAME}]\n"
        "type = onedrive\n"
        f"token = {json.dumps(token, separators=(',', ':'))}\n"
        f"drive_id = {drive_id}\n"
        f"drive_type = {drive_type}\n")
    backup.RCLONE_CONF.chmod(0o600)


def unlink() -> None:
    if backup.RCLONE_CONF.exists():
        backup.RCLONE_CONF.unlink()


def test() -> str:
    if not backup.onedrive_linked():
        return "OneDrive is niet gekoppeld"
    p = backup.rclone("about", f"{backup.REMOTE_NAME}:", "--json", timeout=60)
    if p.returncode != 0:
        return "Verbinding mislukt: " + (p.stderr.strip().splitlines() or ["onbekende fout"])[-1]
    info = json.loads(p.stdout or "{}")
    free = info.get("free")
    return "Verbonden met OneDrive" + (f" ({free / 1e9:.1f} GB vrij)" if free else "")
