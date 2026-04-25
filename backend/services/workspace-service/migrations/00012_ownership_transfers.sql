CREATE TABLE project_ownership_transfers (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    from_user_id UUID NOT NULL,
    to_user_id   UUID NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_pot_project ON project_ownership_transfers(project_id) WHERE status = 'pending';

CREATE TABLE team_ownership_transfers (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id      UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    from_user_id UUID NOT NULL,
    to_user_id   UUID NOT NULL,
    status       TEXT NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tot_team ON team_ownership_transfers(team_id) WHERE status = 'pending';
