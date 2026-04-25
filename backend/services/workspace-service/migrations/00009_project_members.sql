-- +goose Up
CREATE TABLE project_members (
    project_id             UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id                UUID NOT NULL,
    edit_title          BOOLEAN NOT NULL DEFAULT false,
    edit_description    BOOLEAN NOT NULL DEFAULT false,
    edit_tags           BOOLEAN NOT NULL DEFAULT false,
    edit_blockers       BOOLEAN NOT NULL DEFAULT false,
    edit_assignee       BOOLEAN NOT NULL DEFAULT false,
    edit_status         BOOLEAN NOT NULL DEFAULT false,
    share               BOOLEAN NOT NULL DEFAULT false,
    delete_task              BOOLEAN NOT NULL DEFAULT false,
    rename_project      BOOLEAN NOT NULL DEFAULT false,
    manage_members     BOOLEAN NOT NULL DEFAULT false,
    manage_automations BOOLEAN NOT NULL DEFAULT false,
    manage_attachments BOOLEAN NOT NULL DEFAULT false,
    delete_project     BOOLEAN NOT NULL DEFAULT false,
    import_tasks             BOOLEAN NOT NULL DEFAULT false,
    is_frozen_by_tariff    BOOLEAN NOT NULL DEFAULT false,
    joined_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, user_id)
);

CREATE INDEX idx_pm_user_id ON project_members(user_id);

CREATE TABLE project_team_members (
    project_id             UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    team_id                UUID NOT NULL,
    edit_title          BOOLEAN NOT NULL DEFAULT false,
    edit_description    BOOLEAN NOT NULL DEFAULT false,
    edit_tags           BOOLEAN NOT NULL DEFAULT false,
    edit_blockers       BOOLEAN NOT NULL DEFAULT false,
    edit_assignee       BOOLEAN NOT NULL DEFAULT false,
    edit_status         BOOLEAN NOT NULL DEFAULT false,
    share               BOOLEAN NOT NULL DEFAULT false,
    delete_task              BOOLEAN NOT NULL DEFAULT false,
    rename_project      BOOLEAN NOT NULL DEFAULT false,
    manage_members     BOOLEAN NOT NULL DEFAULT false,
    manage_automations BOOLEAN NOT NULL DEFAULT false,
    manage_attachments BOOLEAN NOT NULL DEFAULT false,
    delete_project     BOOLEAN NOT NULL DEFAULT false,
    import_tasks             BOOLEAN NOT NULL DEFAULT false,
    is_frozen_in_project   BOOLEAN NOT NULL DEFAULT false,
    joined_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, team_id)
);

CREATE INDEX idx_ptm_team_id ON project_team_members(team_id);

-- +goose Down
DROP TABLE project_team_members;
DROP TABLE project_members;
