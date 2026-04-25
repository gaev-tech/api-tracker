-- +goose Up
CREATE TABLE task_direct_accesses (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id             UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    grantee_user_id     UUID,
    grantee_team_id     UUID,
    granted_by          UUID NOT NULL,
    edit_title       BOOLEAN NOT NULL DEFAULT false,
    edit_description BOOLEAN NOT NULL DEFAULT false,
    edit_tags        BOOLEAN NOT NULL DEFAULT false,
    edit_blockers    BOOLEAN NOT NULL DEFAULT false,
    edit_assignee    BOOLEAN NOT NULL DEFAULT false,
    edit_status      BOOLEAN NOT NULL DEFAULT false,
    share            BOOLEAN NOT NULL DEFAULT false,
    delete_task           BOOLEAN NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_exactly_one_grantee CHECK (
        (grantee_user_id IS NOT NULL AND grantee_team_id IS NULL)
        OR (grantee_user_id IS NULL AND grantee_team_id IS NOT NULL)
    ),
    CONSTRAINT uq_task_grantee_user UNIQUE (task_id, grantee_user_id),
    CONSTRAINT uq_task_grantee_team UNIQUE (task_id, grantee_team_id)
);

CREATE INDEX idx_tda_task_id ON task_direct_accesses(task_id);
CREATE INDEX idx_tda_grantee_user ON task_direct_accesses(grantee_user_id) WHERE grantee_user_id IS NOT NULL;
CREATE INDEX idx_tda_grantee_team ON task_direct_accesses(grantee_team_id) WHERE grantee_team_id IS NOT NULL;

-- +goose Down
DROP TABLE task_direct_accesses;
