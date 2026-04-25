package handler

import (
	"database/sql"
	"errors"
	"net/http"
	"strings"

	"github.com/gaev-tech/api-tracker/backend/pkg/outbox"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/store"
	"github.com/gin-gonic/gin"
)

type TeamHandler struct {
	teams   *store.TeamStore
	members *store.TeamMemberStore
	db      *sql.DB
}

func NewTeamHandler(teams *store.TeamStore, members *store.TeamMemberStore, db *sql.DB) *TeamHandler {
	return &TeamHandler{teams: teams, members: members, db: db}
}

// CreateTeam godoc: POST /teams
func (h *TeamHandler) CreateTeam(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)

	var req domain.CreateTeamRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}
	req.Name = strings.TrimSpace(req.Name)
	if req.Name == "" {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", "name is required", nil))
		return
	}

	tx, err := h.db.BeginTx(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	team, err := h.teams.Create(c.Request.Context(), tx, uid, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to create team", nil))
		return
	}

	// Add owner as admin member
	if err := h.members.AddMember(c.Request.Context(), tx, team.ID, uid, domain.TeamRoleAdmin); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to add owner as member", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "workspace_outbox", "workspace.team.created", map[string]string{
		"team_id":  team.ID,
		"owner_id": uid,
	}); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusCreated, team)
}

// ListTeams godoc: GET /teams
func (h *TeamHandler) ListTeams(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)

	params := &domain.TeamListParams{
		OwnerID: uid,
		Cursor:  c.Query("cursor"),
		Limit:   parseLimit(c, 50, 100),
	}

	result, err := h.teams.ListByOwner(c.Request.Context(), params)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusOK, result)
}

// GetTeam godoc: GET /teams/:id
func (h *TeamHandler) GetTeam(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	teamID := c.Param("id")

	team, err := h.teams.FindByID(c.Request.Context(), teamID)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	if team.OwnerID != uid {
		c.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}

	c.JSON(http.StatusOK, team)
}

// UpdateTeam godoc: PATCH /teams/:id
func (h *TeamHandler) UpdateTeam(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	teamID := c.Param("id")

	var req domain.UpdateTeamRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	if req.Name != nil {
		trimmed := strings.TrimSpace(*req.Name)
		if trimmed == "" {
			c.JSON(http.StatusBadRequest, apiErr("validation_error", "name cannot be empty", nil))
			return
		}
		req.Name = &trimmed
	}

	// Verify ownership
	existing, err := h.teams.FindByID(c.Request.Context(), teamID)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if existing.OwnerID != uid {
		c.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}

	tx, err := h.db.BeginTx(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	team, err := h.teams.Update(c.Request.Context(), tx, teamID, &req)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update team", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "workspace_outbox", "workspace.team.updated", map[string]string{
		"team_id":  team.ID,
		"owner_id": uid,
	}); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusOK, team)
}

// DeleteTeam godoc: DELETE /teams/:id
func (h *TeamHandler) DeleteTeam(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	teamID := c.Param("id")

	// Verify ownership
	existing, err := h.teams.FindByID(c.Request.Context(), teamID)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if existing.OwnerID != uid {
		c.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}

	tx, err := h.db.BeginTx(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := h.teams.Delete(c.Request.Context(), tx, teamID); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to delete team", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "workspace_outbox", "workspace.team.deleted", map[string]string{
		"team_id":  teamID,
		"owner_id": uid,
	}); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.Status(http.StatusNoContent)
}
