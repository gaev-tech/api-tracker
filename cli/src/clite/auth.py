"""Credentials хранение и refresh (terminal-only auth flow, ARCH §4.3)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

CREDENTIALS_PATH = Path.home() / ".config" / "clite" / "credentials.yaml"


@dataclass(frozen=True)
class Credentials:
    access_token: str
    refresh_token: str
    user_email: str
    expires_at: int  # unix timestamp

    @property
    def expired(self) -> bool:
        return time.time() >= self.expires_at - 30  # 30 sec safety


def load_credentials() -> Credentials | None:
    if not CREDENTIALS_PATH.exists():
        return None
    try:
        with CREDENTIALS_PATH.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return Credentials(
            access_token=str(data["access_token"]),
            refresh_token=str(data["refresh_token"]),
            user_email=str(data["user_email"]),
            expires_at=int(data["expires_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def save_credentials(creds: Credentials) -> None:
    CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CREDENTIALS_PATH.open("w", encoding="utf-8") as f:
        yaml.safe_dump(asdict(creds), f)
    os.chmod(CREDENTIALS_PATH, 0o600)


def delete_credentials() -> bool:
    if not CREDENTIALS_PATH.exists():
        return False
    CREDENTIALS_PATH.unlink()
    return True


def decode_jwt_claims(token: str) -> dict[str, object]:
    """Простой decode JWT payload без верификации (для UI/whoami)."""
    import base64

    parts = token.split(".")
    if len(parts) != 3:
        return {}
    payload_b64 = parts[1]
    padding = "=" * (-len(payload_b64) % 4)
    try:
        payload = base64.urlsafe_b64decode(payload_b64 + padding)
        return dict(json.loads(payload))
    except (ValueError, json.JSONDecodeError):
        return {}
