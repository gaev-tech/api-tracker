-- +goose Up
CREATE TABLE events (
    id               UUID NOT NULL DEFAULT gen_random_uuid(),
    type             TEXT NOT NULL,
    actor_id         UUID,
    task_id          UUID,
    project_id       UUID,
    team_id          UUID,
    automation_id    UUID,
    target_user_id   UUID,
    payload          JSONB NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);

-- Function to dynamically create monthly partitions
CREATE OR REPLACE FUNCTION ensure_events_partition(ts TIMESTAMPTZ)
RETURNS VOID AS $$
DECLARE
    partition_name TEXT;
    start_date     DATE;
    end_date       DATE;
BEGIN
    start_date := date_trunc('month', ts)::DATE;
    end_date := (start_date + INTERVAL '1 month')::DATE;
    partition_name := 'events_' || to_char(start_date, 'YYYY_MM');

    IF NOT EXISTS (
        SELECT 1 FROM pg_class WHERE relname = partition_name
    ) THEN
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF events FOR VALUES FROM (%L) TO (%L)',
            partition_name, start_date, end_date
        );
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Create partition for current month
SELECT ensure_events_partition(now());

-- +goose Down
DROP FUNCTION IF EXISTS ensure_events_partition;
DROP TABLE IF EXISTS events;
