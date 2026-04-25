-- +goose Up
CREATE TABLE project_invitations (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id         UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    invitee_user_id    UUID,
    invitee_team_id    UUID,
    invited_by         UUID NOT NULL,
    edit_title         BOOLEAN NOT NULL DEFAULT false,
    edit_description   BOOLEAN NOT NULL DEFAULT false,
    edit_tags          BOOLEAN NOT NULL DEFAULT false,
    edit_blockers      BOOLEAN NOT NULL DEFAULT false,
    edit_assignee      BOOLEAN NOT NULL DEFAULT false,
    edit_status        BOOLEAN NOT NULL DEFAULT false,
    share              BOOLEAN NOT NULL DEFAULT false,
    delete_task        BOOLEAN NOT NULL DEFAULT false,
    rename_project     BOOLEAN NOT NULL DEFAULT false,
    manage_members     BOOLEAN NOT NULL DEFAULT false,
    manage_automations BOOLEAN NOT NULL DEFAULT false,
    manage_attachments BOOLEAN NOT NULL DEFAULT false,
    delete_project     BOOLEAN NOT NULL DEFAULT false,
    import_tasks       BOOLEAN NOT NULL DEFAULT false,
    status             TEXT NOT NULL DEFAULT 'pending',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_pi_exactly_one_invitee CHECK (
        (invitee_user_id IS NOT NULL AND invitee_team_id IS NULL)
        OR (invitee_user_id IS NULL AND invitee_team_id IS NOT NULL)
    )
);

CREATE TABLE team_invitations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id         UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    invitee_user_id UUID NOT NULL,
    invited_by      UUID NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- +goose Down
DROP TABLE team_invitations;
DROP TABLE project_invitations;
