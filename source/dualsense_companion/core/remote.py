"""Opt-in remote pairing and cookie session authority.

Only digests of pairing codes/session secrets are persisted.  Raw tokens are
returned once to the local pairing flow and are never included in diagnostics,
events, URLs or logs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

SESSION_COOKIE = "ds5forge_session"
PAIRING_TTL_SECONDS = 300
SESSION_TTL_SECONDS = 86_400


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def is_loopback_host(host: str | None) -> bool:
    """Return whether a Host header names the local loopback interface.

    An origin-less request is only treated as trusted local access when it
    targets loopback.  Any other Host is an unknown remote client and must
    authenticate; this keeps the tunnel from failing open when a forwarded
    Host does not exactly match a registered origin.
    """

    if not host:
        return False
    value = host.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        if end == -1:
            return False
        hostname = value[1:end]
    elif value.count(":") > 1:
        # Bare IPv6 literal without an explicit port.
        hostname = value
    else:
        hostname = value.split(":", 1)[0]
    return hostname in {"127.0.0.1", "localhost", "::1"}


def validate_remote_origin(origin: str) -> str:
    value = origin.strip()
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("remote origin must be an HTTPS origin without credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("remote origin must not contain a path, query or fragment")
    host = parsed.hostname.lower()
    try:
        port_value = parsed.port
    except ValueError as exc:
        raise ValueError("remote origin contains an invalid port") from exc
    # Canonicalize the default HTTPS port so browser Origin and Host headers
    # compare equal whether the user typed :443 or omitted it.
    port = f":{port_value}" if port_value not in {None, 443} else ""
    if ":" in host:
        host = f"[{host}]"
    return f"https://{host}{port}"


@dataclass(frozen=True, slots=True)
class PairingChallenge:
    pairing_id: str
    code: str
    expires_at: float
    origin_hint: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "pairing_id": self.pairing_id,
            "code": self.code,
            "expires_at": self.expires_at,
            "origin_hint": self.origin_hint,
        }


@dataclass(frozen=True, slots=True)
class RemoteSession:
    session_id: str
    token_digest: str
    origin: str
    created_at: float
    expires_at: float
    revoked: bool = False

    def public_dict(self, now: float) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "origin": self.origin,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "expired": now >= self.expires_at,
            "revoked": self.revoked,
        }


class RemoteAccessManager:
    def __init__(self, persistence_path: str | Path | None = None, *, now: Callable[[], float] = time.time) -> None:
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self.now = now
        self.enabled = False
        self._pairings: dict[str, tuple[str, float, str | None]] = {}
        self._sessions: dict[str, RemoteSession] = {}
        self._origins: set[str] = set()
        self._load()

    def _load(self) -> None:
        if self.persistence_path is None or not self.persistence_path.exists():
            return
        try:
            payload = json.loads(self.persistence_path.read_text(encoding="utf-8"))
            self.enabled = bool(payload.get("enabled", False))
            self._origins = {validate_remote_origin(value) for value in payload.get("origins", [])}
            for item in payload.get("sessions", []):
                session = RemoteSession(**item)
                self._sessions[session.session_id] = session
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # Invalid session state is fail-closed and recoverable by pairing.
            self.enabled = False
            self._origins.clear()
            self._sessions.clear()

    def _save(self) -> None:
        if self.persistence_path is None:
            return
        self.persistence_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "enabled": self.enabled,
            "origins": sorted(self._origins),
            "sessions": [
                {
                    "session_id": session.session_id,
                    "token_digest": session.token_digest,
                    "origin": session.origin,
                    "created_at": session.created_at,
                    "expires_at": session.expires_at,
                    "revoked": session.revoked,
                }
                for session in self._sessions.values()
            ],
        }
        temporary = self.persistence_path.with_suffix(self.persistence_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        temporary.replace(self.persistence_path)

    def start_pairing(self, *, origin_hint: str | None = None, ttl: int = PAIRING_TTL_SECONDS) -> PairingChallenge:
        if origin_hint is not None:
            origin_hint = validate_remote_origin(origin_hint)
        code = f"{secrets.randbelow(1_000_000):06d}"
        challenge = PairingChallenge(str(uuid.uuid4()), code, self.now() + max(30, ttl), origin_hint)
        self._pairings[challenge.pairing_id] = (_digest(code), challenge.expires_at, origin_hint)
        return challenge

    def complete_pairing(self, pairing_id: str, code: str, origin: str) -> tuple[RemoteSession, str]:
        origin = validate_remote_origin(origin)
        record = self._pairings.pop(pairing_id, None)
        if (
            record is None
            or self.now() >= record[1]
            or (record[2] is not None and record[2] != origin)
            or not hmac.compare_digest(record[0], _digest(code))
        ):
            raise ValueError("pairing challenge is invalid or expired")
        token = secrets.token_urlsafe(32)
        now = self.now()
        session = RemoteSession(str(uuid.uuid4()), _digest(token), origin, now, now + SESSION_TTL_SECONDS)
        self._sessions[session.session_id] = session
        self._origins.add(origin)
        self.enabled = True
        self._save()
        return session, token

    def authenticate(self, token: str | None, origin: str | None) -> bool:
        if not self.enabled or not token or not origin:
            return False
        try:
            normalized_origin = validate_remote_origin(origin)
        except ValueError:
            return False
        if normalized_origin not in self._origins:
            return False
        digest = _digest(token)
        now = self.now()
        for session in self._sessions.values():
            if session.revoked or now >= session.expires_at or session.origin != normalized_origin:
                continue
            if hmac.compare_digest(session.token_digest, digest):
                return True
        return False

    def revoke(self, session_id: str) -> bool:
        session = self._sessions.get(session_id)
        if session is None:
            return False
        self._sessions[session_id] = RemoteSession(
            session.session_id,
            session.token_digest,
            session.origin,
            session.created_at,
            session.expires_at,
            True,
        )
        self._save()
        return True

    def disable(self) -> None:
        self.enabled = False
        self._sessions.clear()
        self._pairings.clear()
        self._origins.clear()
        self._save()

    def status(self) -> dict[str, Any]:
        now = self.now()
        active = [session for session in self._sessions.values() if self.authenticate_tokenless(session)]
        if not self.enabled:
            status = "off"
        elif active:
            status = "online"
        elif self._sessions and all(session.revoked for session in self._sessions.values()):
            status = "revoked"
        elif self._sessions and all(now >= session.expires_at for session in self._sessions.values()):
            status = "expired"
        else:
            status = "degraded"
        return {
            "enabled": self.enabled,
            "status": status,
            "origins": sorted(self._origins),
            "sessions": [session.public_dict(now) for session in self._sessions.values()],
            "pairing_active": any(now < expires for _digest_value, expires, _origin in self._pairings.values()),
        }

    def authenticate_tokenless(self, session: RemoteSession) -> bool:
        return not session.revoked and self.now() < session.expires_at

    def has_active_session(self) -> bool:
        return self.enabled and any(self.authenticate_tokenless(session) for session in self._sessions.values())

    def cookie_header(self, token: str) -> str:
        # Secure/HttpOnly/SameSite are intentional; a token is never put in a URL.
        return f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_TTL_SECONDS}; HttpOnly; Secure; SameSite=Strict"

    @staticmethod
    def token_from_cookie(header: str | None) -> str | None:
        if not header:
            return None
        for item in header.split(";"):
            name, separator, value = item.strip().partition("=")
            if separator and name == SESSION_COOKIE:
                return value or None
        return None

    def origin_allowed(self, origin: str | None) -> bool:
        if not origin:
            return False
        try:
            return validate_remote_origin(origin) in self._origins
        except ValueError:
            return False

    def origin_for_host(self, host: str | None) -> str | None:
        """Resolve a registered remote origin from an exact Host header.

        A tunnel request may be made by a non-browser client and therefore
        carry no Origin header.  Matching the registered HTTPS origin's
        netloc keeps that path authenticated without treating an arbitrary
        Host header as remote access.
        """
        if not host:
            return None
        candidate = host.strip().lower()
        if candidate.endswith(":443"):
            candidate = candidate[:-4]
        for origin in self._origins:
            if urlsplit(origin).netloc.lower() == candidate:
                return origin
        return None
