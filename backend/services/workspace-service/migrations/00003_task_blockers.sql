-- +goose Up
CREATE TABLE task_blockers (
    task_id          UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    blocking_task_id UUID NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (task_id, blocking_task_id),
    CHECK (task_id != blocking_task_id)
);

CREATE INDEX idx_task_blockers_blocking ON task_blockers(blocking_task_id);

-- +goose Down
DROP TABLE task_blockers;
