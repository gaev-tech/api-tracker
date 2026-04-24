-- +goose Up
CREATE TABLE task_projects (
    task_id    UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    project_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (task_id, project_id)
);

CREATE INDEX idx_task_projects_project_id ON task_projects(project_id);

-- +goose Down
DROP TABLE task_projects;
