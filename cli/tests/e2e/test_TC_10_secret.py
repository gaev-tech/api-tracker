"""TC 10.x — clite create/get/delete secret (M3+, verb-first)."""

from __future__ import annotations

import json
import re

KEY_RE = re.compile(r"[0-9a-f]{40}")


def _create_project(clite, name: str) -> str:
    r = clite(["create", "project", "--name", name, "--output", "json"])
    assert r.returncode == 0, r.stderr
    return str(json.loads(r.stdout)["id"])


def test_TC_10_1_1_secret_set(clite):
    """10.1.1 — create secret --project <key> --name token --value <plain> → exit 0."""
    project_id = _create_project(clite, "TC-10.1.1-proj")
    r = clite(
        [
            "create",
            "secret",
            "--project",
            project_id,
            "--name",
            "token",
            "--value",
            "s3cr3t",
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert KEY_RE.fullmatch(data["id"])
    assert data["name"] == "token"
    # value НЕ должен возвращаться в API.
    assert "value" not in data


def test_TC_10_1_2_secret_overwrite(clite):
    """10.1.2 — перезапись существующего секрета → exit 0."""
    project_id = _create_project(clite, "TC-10.1.2-proj")
    r1 = clite(
        [
            "create",
            "secret",
            "--project",
            project_id,
            "--name",
            "k",
            "--value",
            "v1",
            "--output",
            "json",
        ]
    )
    assert r1.returncode == 0
    r2 = clite(
        [
            "create",
            "secret",
            "--project",
            project_id,
            "--name",
            "k",
            "--value",
            "v2",
            "--output",
            "json",
        ]
    )
    assert r2.returncode == 0


def test_TC_10_3_1_secret_list(clite):
    """10.3.1 — get secrets --project <key> → exit 0, имена БЕЗ значений."""
    project_id = _create_project(clite, "TC-10.3.1-proj")
    clite(
        [
            "create",
            "secret",
            "--project",
            project_id,
            "--name",
            "alpha",
            "--value",
            "X",
        ]
    )
    clite(
        [
            "create",
            "secret",
            "--project",
            project_id,
            "--name",
            "beta",
            "--value",
            "Y",
        ]
    )
    lst = clite(["get", "secrets", "--project", project_id, "--output", "json"])
    assert lst.returncode == 0, lst.stderr
    data = json.loads(lst.stdout)
    names = {s["name"] for s in data}
    assert names == {"alpha", "beta"}
    for s in data:
        assert "value" not in s
        assert "value_encrypted" not in s


def test_TC_10_4_1_secret_delete(clite):
    """10.4.1 — delete secret <key> --project <p> → exit 0; не в списке."""
    project_id = _create_project(clite, "TC-10.4.1-proj")
    create_r = clite(
        [
            "create",
            "secret",
            "--project",
            project_id,
            "--name",
            "to-go",
            "--value",
            "X",
            "--output",
            "json",
        ]
    )
    sid = json.loads(create_r.stdout)["id"]
    r = clite(["delete", "secret", sid, "--project", project_id])
    assert r.returncode == 0, r.stderr
    lst = clite(["get", "secrets", "--project", project_id, "--output", "json"])
    ids = [s["id"] for s in json.loads(lst.stdout)]
    assert sid not in ids
