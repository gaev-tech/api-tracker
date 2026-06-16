"""SHA1-based entity ids (PRD §5.2.6, ARCH §3.7)."""

from hashlib import sha1


def user_id_for(email: str) -> str:
    """SHA1(email lowercased) — стабильно одинаков для одного email
    в схемах auth и tasks независимо (ARCH §3.7.1.1)."""
    data = email.strip().lower().encode("utf-8")
    return sha1(data, usedforsecurity=False).hexdigest()
