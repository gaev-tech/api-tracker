"""TC 9.x — clite create/get/update/delete/run automation (M3+, verb-first)."""

from __future__ import annotations

import json
import re

KEY_RE = re.compile(r"[0-9a-f]{40}")


def _create_project(clite, name: str) -> str:
    r = clite(["create", "project", "--name", name, "--output", "json"])
    assert r.returncode == 0, r.stderr
    return str(json.loads(r.stdout)["id"])


def test_TC_9_1_1_create_cron_webhook_automation(clite):
    """9.1.1 — cron-trigger + webhook action → exit 0, SHA1-ключ."""
    project_id = _create_project(clite, "TC-9.1.1-proj")
    r = clite(
        [
            "create",
            "automation",
            "--project",
            project_id,
            "--name",
            "morning",
            "--trigger-type",
            "cron",
            "--trigger-config",
            json.dumps({"cron": "0 9 * * *"}),
            "--action-type",
            "webhook",
            "--action-config",
            json.dumps(
                {
                    "url": "https://example.com/hook",
                    "headers": {"Content-Type": "application/json"},
                    "body": '{"hello":"world"}',
                }
            ),
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert KEY_RE.fullmatch(data["id"])
    assert data["trigger_type"] == "cron"
    assert data["action_type"] == "webhook"


def test_TC_9_1_2_create_event_system_method_automation(clite):
    """9.1.2 — event-trigger + system_method action."""
    project_id = _create_project(clite, "TC-9.1.2-proj")
    r = clite(
        [
            "create",
            "automation",
            "--project",
            project_id,
            "--name",
            "on-done",
            "--trigger-type",
            "event",
            "--trigger-config",
            json.dumps({"event_type": "task.status_changed", "filter": "status==done"}),
            "--action-type",
            "system_method",
            "--action-config",
            json.dumps({"method": "tasks.list", "args": {"filter": "status==done"}}),
            "--output",
            "json",
        ]
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["trigger_type"] == "event"
    assert data["action_type"] == "system_method"


def test_TC_9_2_2_invalid_cron_returns_error(clite):
    """9.2.2 — невалидный cron → exit 1 (server 400)."""
    project_id = _create_project(clite, "TC-9.2.2-proj")
    r = clite(
        [
            "create",
            "automation",
            "--project",
            project_id,
            "--name",
            "bad",
            "--trigger-type",
            "cron",
            "--trigger-config",
            json.dumps({"cron": "not-a-cron"}),
            "--action-type",
            "webhook",
            "--action-config",
            json.dumps({"url": "https://example.com/x", "body": ""}),
        ]
    )
    assert r.returncode != 0


def test_TC_9_2_4_system_method_not_in_whitelist(clite):
    """9.2.4 — system_method не в whitelist → exit 1 (server 400)."""
    project_id = _create_project(clite, "TC-9.2.4-proj")
    r = clite(
        [
            "create",
            "automation",
            "--project",
            project_id,
            "--name",
            "evil",
            "--trigger-type",
            "event",
            "--trigger-config",
            json.dumps({"event_type": "task.created"}),
            "--action-type",
            "system_method",
            "--action-config",
            json.dumps({"method": "os.system", "args": {}}),
        ]
    )
    assert r.returncode != 0


def test_TC_9_3_1_run_now(clite):
    """9.3.1 — run automation <key> → exit 0, stdout с результатом action."""
    project_id = _create_project(clite, "TC-9.3.1-proj")
    create_r = clite(
        [
            "create",
            "automation",
            "--project",
            project_id,
            "--name",
            "now",
            "--trigger-type",
            "event",
            "--trigger-config",
            json.dumps({"event_type": "task.created"}),
            "--action-type",
            "system_method",
            "--action-config",
            json.dumps({"method": "tasks.list", "args": {}}),
            "--output",
            "json",
        ]
    )
    assert create_r.returncode == 0, create_r.stderr
    aid = json.loads(create_r.stdout)["id"]
    r = clite(["run", "automation", aid, "--output", "json"])
    assert r.returncode == 0, r.stderr
    # system_method execute_automation: { status: "ok", result: ... }
    data = json.loads(r.stdout)
    assert "status" in data


def test_TC_9_4_1_delete_automation(clite):
    """9.4.1 — delete automation <key> → exit 0; больше не в list."""
    project_id = _create_project(clite, "TC-9.4.1-proj")
    create_r = clite(
        [
            "create",
            "automation",
            "--project",
            project_id,
            "--name",
            "doomed",
            "--trigger-type",
            "event",
            "--trigger-config",
            json.dumps({"event_type": "task.created"}),
            "--action-type",
            "system_method",
            "--action-config",
            json.dumps({"method": "tasks.list", "args": {}}),
            "--output",
            "json",
        ]
    )
    aid = json.loads(create_r.stdout)["id"]
    r = clite(["delete", "automation", aid])
    assert r.returncode == 0, r.stderr
    # Подтверждаем, что в списке его больше нет.
    lst = clite(["get", "automations", "--project", project_id, "--output", "json"])
    assert lst.returncode == 0, lst.stderr
    ids = [a["id"] for a in json.loads(lst.stdout)]
    assert aid not in ids


def test_TC_9_list_and_get(clite):
    """Дополнительно — get automations / get automation <key> работают."""
    project_id = _create_project(clite, "TC-9-list-proj")
    create_r = clite(
        [
            "create",
            "automation",
            "--project",
            project_id,
            "--name",
            "listed",
            "--trigger-type",
            "cron",
            "--trigger-config",
            json.dumps({"cron": "0 0 * * *"}),
            "--action-type",
            "webhook",
            "--action-config",
            json.dumps({"url": "https://example.com/", "body": ""}),
            "--output",
            "json",
        ]
    )
    aid = json.loads(create_r.stdout)["id"]
    lst = clite(["get", "automations", "--project", project_id, "--output", "json"])
    assert lst.returncode == 0
    assert any(a["id"] == aid for a in json.loads(lst.stdout))

    one = clite(["get", "automation", aid, "--output", "json"])
    assert one.returncode == 0
    assert json.loads(one.stdout)["id"] == aid
