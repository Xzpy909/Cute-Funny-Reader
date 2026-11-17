"""Accounts & sessions.

Every account owns a folder in /data (named after its e-mail) that holds its libraries.
The first account is the admin: it can add / remove accounts and hand the admin role over.
Passwords are stored as PBKDF2-SHA256 hashes; sessions are signed cookies.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import uuid
from pathlib import Path

PBKDF2_ROUNDS = 310_000
SESSION_DAYS = 60
COOKIE = "cf_session"
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _hash(password: str, salt: bytes) -> str:
    return _b64(hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS))


def folder_for(email: str, taken: set[str]) -> str:
    base = re.sub(r"[^\w.+-]+", "_", email.strip().lower().split("@")[0]).strip("._") or "user"
    name, n = base, 2
    while name.lower() in taken:
        name, n = f"{base}-{n}", n + 1
    return name


class Accounts:
    def __init__(self, config_dir: Path):
        self.file = config_dir / "accounts.json"
        self.lock = threading.RLock()
        key_file = config_dir / "secret.key"
        if not key_file.exists():
            key_file.write_bytes(secrets.token_bytes(32))
            try:
                key_file.chmod(0o600)
            except OSError:
                pass
        self.key = key_file.read_bytes()
        try:
            self.items: list[dict] = json.loads(self.file.read_text("utf-8"))
        except Exception:
            self.items = []

    # ---- storage
    def _save(self):
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.items, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(self.file)

    def public(self, a: dict) -> dict:
        return {"id": a["id"], "email": a["email"], "folder": a["folder"], "admin": bool(a.get("admin")), "created": a.get("created")}

    def get(self, uid: str) -> dict | None:
        return next((a for a in self.items if a["id"] == uid), None)

    def by_email(self, email: str) -> dict | None:
        e = (email or "").strip().lower()
        return next((a for a in self.items if a["email"].lower() == e), None)

    def folders(self) -> set[str]:
        return {a["folder"].lower() for a in self.items}

    # ---- accounts
    @staticmethod
    def _check(email: str, password: str):
        email = (email or "").strip()
        if not EMAIL_RE.match(email) or len(email) > 200:
            raise ValueError("Enter a valid e-mail address")
        if len(password or "") < 8:
            raise ValueError("Use a password with at least 8 characters")
        return email

    def create(self, email: str, password: str, admin: bool = False) -> dict:
        email = self._check(email, password)
        with self.lock:
            if self.by_email(email):
                raise ValueError("There's already an account with that e-mail")
            salt = secrets.token_bytes(16)
            a = {"id": uuid.uuid4().hex[:12], "email": email, "folder": folder_for(email, self.folders()),
                 "salt": _b64(salt), "hash": _hash(password, salt), "admin": admin or not self.items,
                 "sv": 1, "created": int(time.time())}
            self.items.append(a)
            self._save()
        return a

    def verify(self, email: str, password: str) -> dict | None:
        a = self.by_email(email)
        if not a:
            _hash(password or "", b"x" * 16)                 # same work either way (no account probing by timing)
            return None
        salt = base64.urlsafe_b64decode(a["salt"] + "==")
        return a if hmac.compare_digest(_hash(password or "", salt), a["hash"]) else None

    def set_password(self, uid: str, password: str):
        a = self.get(uid)
        if not a:
            raise KeyError(uid)
        self._check(a["email"], password)
        with self.lock:
            salt = secrets.token_bytes(16)
            a.update(salt=_b64(salt), hash=_hash(password, salt), sv=a.get("sv", 1) + 1)   # logs out other sessions
            self._save()

    def delete(self, uid: str) -> dict:
        with self.lock:
            a = self.get(uid)
            if not a:
                raise KeyError(uid)
            if a.get("admin"):
                raise ValueError("Hand the admin role to another account before deleting this one")
            self.items = [x for x in self.items if x["id"] != uid]
            self._save()
        return a

    def transfer_admin(self, from_uid: str, to_uid: str):
        with self.lock:
            src, dst = self.get(from_uid), self.get(to_uid)
            if not src or not dst:
                raise KeyError(to_uid)
            if not src.get("admin"):
                raise PermissionError("Only the admin can do that")
            if src is dst:
                return
            src["admin"], dst["admin"] = False, True
            self._save()

    # ---- sessions
    def _sign(self, msg: str) -> str:
        return _b64(hmac.new(self.key, msg.encode(), hashlib.sha256).digest())

    def token(self, a: dict) -> str:
        msg = f"{a['id']}.{int(time.time()) + SESSION_DAYS * 86400}.{a.get('sv', 1)}"
        return f"{msg}.{self._sign(msg)}"

    def from_token(self, tok: str | None) -> dict | None:
        try:
            uid, exp, sv, sig = (tok or "").split(".")
        except ValueError:
            return None
        if not hmac.compare_digest(sig, self._sign(f"{uid}.{exp}.{sv}")) or int(exp) < time.time():
            return None
        a = self.get(uid)
        return a if a and str(a.get("sv", 1)) == sv else None
