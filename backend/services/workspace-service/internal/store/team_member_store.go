package store

import (
	"context"
	"database/sql"
	"errors"

	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
)

type TeamMemberStore struct {
	db *sql.DB
}

func NewTeamMemberStore(db *sql.DB) *TeamMemberStore {
	return &TeamMemberStore{db: db}
}

// AddMember inserts a user into a team.
func (store *TeamMemberStore) AddMember(ctx context.Context, tx *sql.Tx, teamID, userID, role string) error {
	_, err := tx.ExecContext(ctx, `
		INSERT INTO team_members (team_id, user_id, role)
		VALUES ($1, $2, $3)`,
		teamID, userID, role,
	)
	if isPgUniqueViolation(err) {
		return ErrConflict
	}
	return err
}

// ListMembers returns all members of a team with email/name from users_cache.
func (store *TeamMemberStore) ListMembers(ctx context.Context, teamID string) ([]*domain.TeamMember, error) {
	rows, err := store.db.QueryContext(ctx, `
		SELECT tm.team_id, tm.user_id, COALESCE(uc.email, ''), COALESCE(uc.name, ''),
			tm.role, tm.joined_at
		FROM team_members tm
		LEFT JOIN users_cache uc ON uc.user_id = tm.user_id
		WHERE tm.team_id = $1
		ORDER BY tm.joined_at`, teamID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var members []*domain.TeamMember
	for rows.Next() {
		member := &domain.TeamMember{}
		if err := rows.Scan(
			&member.TeamID, &member.UserID, &member.Email, &member.Name,
			&member.Role, &member.JoinedAt,
		); err != nil {
			return nil, err
		}
		members = append(members, member)
	}
	return members, rows.Err()
}

// UpdateRole updates a team member's role.
func (store *TeamMemberStore) UpdateRole(ctx context.Context, tx *sql.Tx, teamID, userID, role string) (*domain.TeamMember, error) {
	member := &domain.TeamMember{}
	err := tx.QueryRowContext(ctx, `
		UPDATE team_members SET role = $3
		WHERE team_id = $1 AND user_id = $2
		RETURNING team_id, user_id, role, joined_at`,
		teamID, userID, role,
	).Scan(&member.TeamID, &member.UserID, &member.Role, &member.JoinedAt)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, ErrNotFound
	}
	return member, err
}

// RemoveMember removes a user from a team.
func (store *TeamMemberStore) RemoveMember(ctx context.Context, tx *sql.Tx, teamID, userID string) error {
	result, err := tx.ExecContext(ctx, `DELETE FROM team_members WHERE team_id = $1 AND user_id = $2`, teamID, userID)
	if err != nil {
		return err
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if rowsAffected == 0 {
		return ErrNotFound
	}
	return nil
}

// GetUserTeamIDs returns all team IDs that a user belongs to.
func (store *TeamMemberStore) GetUserTeamIDs(ctx context.Context, userID string) ([]string, error) {
	rows, err := store.db.QueryContext(ctx, `SELECT team_id FROM team_members WHERE user_id = $1`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var teamIDs []string
	for rows.Next() {
		var teamID string
		if err := rows.Scan(&teamID); err != nil {
			return nil, err
		}
		teamIDs = append(teamIDs, teamID)
	}
	return teamIDs, rows.Err()
}
