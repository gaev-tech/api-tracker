"""sha1 entity ids — all PKs/FKs become CHAR(40) SHA1 (PRD §5.2, ARCH §3.7)

Revision ID: 20260616_1700
Revises: 20260613_1700
Create Date: 2026-06-16 17:00:00

Маппинг id (формула SHA1, разделитель \\n):
  users.id        SHA1(lower(email))
  tasks.id        SHA1(title, description_md, created_at_ns)
  teams.id        SHA1(name, created_at_ns)
  projects.id     SHA1(name, created_at_ns)
  audit_events.id SHA1(actor_user_id, target_type, target_id,
                       event_type, created_at_ns)

Все FK обновляются по соответствующей мапе. Migration однонаправленная.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260616_1700"
down_revision: str | None = "20260613_1700"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Имена FK, которые мы дропаем и пересоздаём. (table, constraint_name).
_FK_DROPS: list[tuple[str, str]] = [
    ("tasks", "tasks_assignee_id_fkey"),
    ("audit_events", "audit_events_actor_user_id_fkey"),
    ("task_blockers", "task_blockers_task_id_fkey"),
    ("task_blockers", "task_blockers_blocked_by_task_id_fkey"),
    ("task_user_shares", "task_user_shares_task_id_fkey"),
    ("task_user_shares", "task_user_shares_user_id_fkey"),
    ("task_team_shares", "task_team_shares_task_id_fkey"),
    ("task_team_shares", "task_team_shares_team_id_fkey"),
    ("team_members", "team_members_team_id_fkey"),
    ("team_members", "team_members_user_id_fkey"),
    ("project_user_members", "project_user_members_project_id_fkey"),
    ("project_user_members", "project_user_members_user_id_fkey"),
    ("project_team_members", "project_team_members_project_id_fkey"),
    ("project_team_members", "project_team_members_team_id_fkey"),
    ("project_tasks", "project_tasks_project_id_fkey"),
    ("project_tasks", "project_tasks_task_id_fkey"),
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # 1. Добавляем _new колонки и заполняем SHA1.
    op.execute("ALTER TABLE users ADD COLUMN id_new VARCHAR(40)")
    op.execute("UPDATE users SET id_new = encode(digest(lower(email), 'sha1'), 'hex')")

    op.execute("ALTER TABLE tasks ADD COLUMN id_new VARCHAR(40)")
    op.execute(
        "UPDATE tasks SET id_new = encode(digest("
        "title || E'\\n' || description_md || E'\\n' || "
        "(EXTRACT(EPOCH FROM created_at)*1000000000)::bigint::text"
        ", 'sha1'), 'hex')"
    )

    op.execute("ALTER TABLE teams ADD COLUMN id_new VARCHAR(40)")
    op.execute(
        "UPDATE teams SET id_new = encode(digest("
        "name || E'\\n' || (EXTRACT(EPOCH FROM created_at)*1000000000)::bigint::text"
        ", 'sha1'), 'hex')"
    )

    op.execute("ALTER TABLE projects ADD COLUMN id_new VARCHAR(40)")
    op.execute(
        "UPDATE projects SET id_new = encode(digest("
        "name || E'\\n' || (EXTRACT(EPOCH FROM created_at)*1000000000)::bigint::text"
        ", 'sha1'), 'hex')"
    )

    op.execute("ALTER TABLE audit_events ADD COLUMN id_new VARCHAR(40)")
    op.execute(
        "UPDATE audit_events SET id_new = encode(digest("
        "actor_user_id::text || E'\\n' || target_type || E'\\n' || target_id::text "
        "|| E'\\n' || event_type || E'\\n' || "
        "(EXTRACT(EPOCH FROM created_at)*1000000000)::bigint::text"
        ", 'sha1'), 'hex')"
    )

    # 2. Для каждой FK-колонки добавляем _new и заполняем по соответствующему _new.
    _add_fk_new("tasks", "assignee_id", "users")
    _add_fk_new("audit_events", "actor_user_id", "users")
    _add_fk_new("task_blockers", "task_id", "tasks")
    _add_fk_new("task_blockers", "blocked_by_task_id", "tasks")
    _add_fk_new("task_user_shares", "task_id", "tasks")
    _add_fk_new("task_user_shares", "user_id", "users")
    _add_fk_new("task_team_shares", "task_id", "tasks")
    _add_fk_new("task_team_shares", "team_id", "teams")
    _add_fk_new("team_members", "team_id", "teams")
    _add_fk_new("team_members", "user_id", "users")
    _add_fk_new("project_user_members", "project_id", "projects")
    _add_fk_new("project_user_members", "user_id", "users")
    _add_fk_new("project_team_members", "project_id", "projects")
    _add_fk_new("project_team_members", "team_id", "teams")
    _add_fk_new("project_tasks", "project_id", "projects")
    _add_fk_new("project_tasks", "task_id", "tasks")

    # audit_events.target_id — НЕ FK, но FK-семантика на target_type-зависимую таблицу.
    # Используем общую LEFT JOIN: ищем по всем PK-таблицам по target_id::text.
    op.execute("ALTER TABLE audit_events ADD COLUMN target_id_new VARCHAR(40)")
    op.execute(
        "UPDATE audit_events ae SET target_id_new = COALESCE("
        "  (SELECT id_new FROM tasks WHERE id::text = ae.target_id::text), "
        "  (SELECT id_new FROM teams WHERE id::text = ae.target_id::text), "
        "  (SELECT id_new FROM projects WHERE id::text = ae.target_id::text), "
        "  (SELECT id_new FROM users WHERE id::text = ae.target_id::text), "
        "  ae.target_id::text"
        ")"
    )

    # 3. Дропаем FK-констрейнты и старые колонки, заменяем _new.
    for tbl, fk_name in _FK_DROPS:
        op.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {fk_name}")

    # Для всех FK-колонок: удалить старую, переименовать _new → старое имя.
    for tbl, col in (
        ("tasks", "assignee_id"),
        ("audit_events", "actor_user_id"),
        ("task_blockers", "task_id"),
        ("task_blockers", "blocked_by_task_id"),
        ("task_user_shares", "task_id"),
        ("task_user_shares", "user_id"),
        ("task_team_shares", "task_id"),
        ("task_team_shares", "team_id"),
        ("team_members", "team_id"),
        ("team_members", "user_id"),
        ("project_user_members", "project_id"),
        ("project_user_members", "user_id"),
        ("project_team_members", "project_id"),
        ("project_team_members", "team_id"),
        ("project_tasks", "project_id"),
        ("project_tasks", "task_id"),
    ):
        op.execute(f"ALTER TABLE {tbl} DROP COLUMN {col}")
        op.execute(f"ALTER TABLE {tbl} RENAME COLUMN {col}_new TO {col}")
        op.execute(f"ALTER TABLE {tbl} ALTER COLUMN {col} SET NOT NULL")

    # audit_events.target_id (НЕ FK):
    op.execute("ALTER TABLE audit_events DROP COLUMN target_id")
    op.execute("ALTER TABLE audit_events RENAME COLUMN target_id_new TO target_id")
    op.execute("ALTER TABLE audit_events ALTER COLUMN target_id SET NOT NULL")

    # 4. Переключение PK на _new.
    for tbl in ("users", "tasks", "teams", "projects", "audit_events"):
        op.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT {tbl}_pkey")
        op.execute(f"ALTER TABLE {tbl} DROP COLUMN id")
        op.execute(f"ALTER TABLE {tbl} RENAME COLUMN id_new TO id")
        op.execute(f"ALTER TABLE {tbl} ALTER COLUMN id SET NOT NULL")
        # PK для composite-таблиц делается позже отдельно.
    for tbl in ("users", "tasks", "teams", "projects", "audit_events"):
        op.execute(f"ALTER TABLE {tbl} ADD PRIMARY KEY (id)")

    # 5. Composite-таблицы — пересоздаём PK на новых колонках.
    for tbl, cols in (
        ("task_blockers", ("task_id", "blocked_by_task_id")),
        ("team_members", ("team_id", "user_id")),
        ("project_user_members", ("project_id", "user_id")),
        ("project_team_members", ("project_id", "team_id")),
        ("project_tasks", ("project_id", "task_id")),
        ("task_user_shares", ("task_id", "user_id")),
        ("task_team_shares", ("task_id", "team_id")),
    ):
        op.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS {tbl}_pkey")
        cols_sql = ", ".join(cols)
        op.execute(f"ALTER TABLE {tbl} ADD PRIMARY KEY ({cols_sql})")

    # 6. Восстанавливаем FK-констрейнты.
    op.create_foreign_key(
        "tasks_assignee_id_fkey",
        "tasks",
        "users",
        ["assignee_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "audit_events_actor_user_id_fkey",
        "audit_events",
        "users",
        ["actor_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "task_blockers_task_id_fkey",
        "task_blockers",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "task_blockers_blocked_by_task_id_fkey",
        "task_blockers",
        "tasks",
        ["blocked_by_task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "task_user_shares_task_id_fkey",
        "task_user_shares",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "task_user_shares_user_id_fkey",
        "task_user_shares",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "task_team_shares_task_id_fkey",
        "task_team_shares",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "task_team_shares_team_id_fkey",
        "task_team_shares",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "team_members_team_id_fkey",
        "team_members",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "team_members_user_id_fkey",
        "team_members",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "project_user_members_project_id_fkey",
        "project_user_members",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "project_user_members_user_id_fkey",
        "project_user_members",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "project_team_members_project_id_fkey",
        "project_team_members",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "project_team_members_team_id_fkey",
        "project_team_members",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "project_tasks_project_id_fkey",
        "project_tasks",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "project_tasks_task_id_fkey",
        "project_tasks",
        "tasks",
        ["task_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 7. Индексы на target_id пересоздаём (тип сменился).
    op.execute("DROP INDEX IF EXISTS ix_audit_events_target_id")
    op.execute("DROP INDEX IF EXISTS ix_audit_events_target")
    op.execute("CREATE INDEX ix_audit_events_target_id ON audit_events(target_id)")
    op.execute(
        "CREATE INDEX ix_audit_events_target ON "
        "audit_events(target_type, target_id, created_at)"
    )


def _add_fk_new(table: str, col: str, ref_table: str) -> None:
    """Добавляет {col}_new VARCHAR(40) в {table}, заполняет из {ref_table}.id_new."""
    op.execute(f"ALTER TABLE {table} ADD COLUMN {col}_new VARCHAR(40)")
    op.execute(
        f"UPDATE {table} t SET {col}_new = r.id_new "  # noqa: S608
        f"FROM {ref_table} r WHERE t.{col} = r.id"
    )


def downgrade() -> None:
    raise NotImplementedError(
        "sha1 entity-id migration is one-way (PRD §5.2, ARCH §3.7.4)"
    )


_ = sa
