"""SHA1-based entity ids (PRD §5.2.6, ARCH §3.7)."""

import time
from hashlib import sha1

_SEP = "\n"


def user_id_for(email: str) -> str:
    """SHA1(email lowercased) — стабильно одинаков с auth.users.id."""
    data = email.strip().lower().encode("utf-8")
    return sha1(data, usedforsecurity=False).hexdigest()


def new_task_id(title: str, description_md: str) -> str:
    """SHA1(title \\n description \\n time_ns)."""
    return _hash(title, description_md, str(time.time_ns()))


def new_team_id(name: str) -> str:
    return _hash(name, str(time.time_ns()))


def new_project_id(name: str) -> str:
    return _hash(name, str(time.time_ns()))


def new_automation_id(project_id: str, name: str) -> str:
    return _hash(project_id, name, str(time.time_ns()))


def new_secret_id(project_id: str, name: str) -> str:
    return _hash(project_id, name, str(time.time_ns()))


def _hash(*parts: str) -> str:
    return sha1(_SEP.join(parts).encode("utf-8"), usedforsecurity=False).hexdigest()
