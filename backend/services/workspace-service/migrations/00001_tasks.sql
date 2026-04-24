-- +goose Up
CREATE TABLE tasks (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title                TEXT NOT NULL,
    description          TEXT NOT NULL DEFAULT '',
    status               TEXT NOT NULL DEFAULT 'opened',
    author_id            UUID NOT NULL,
    assignee_id          UUID,
    tags                 TEXT[] NOT NULL DEFAULT '{}',
    is_frozen_by_tariff  BOOLEAN NOT NULL DEFAULT false,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_tasks_author_id ON tasks(author_id);
CREATE INDEX idx_tasks_assignee_id ON tasks(assignee_id) WHERE assignee_id IS NOT NULL;
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at);

-- +goose Down
DROP TABLE tasks;
