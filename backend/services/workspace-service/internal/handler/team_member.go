package handler

import (
	"database/sql"
	"errors"
	"net/http"

	"github.com/gaev-tech/api-tracker/backend/pkg/outbox"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/store"
	"github.com/gin-gonic/gin"
)

type TeamMemberHandler struct {
	members *store.TeamMemberStore
	teams   *store.TeamStore
	db      *sql.DB
}

func NewTeamMemberHandler(members *store.TeamMemberStore, teams *store.TeamStore, db *sql.DB) *TeamMemberHandler {
	return &TeamMemberHandler{members: members, teams: teams, db: db}
}

// ListTeamMembers godoc: GET /teams/:id/members
func (handler *TeamMemberHandler) ListTeamMembers(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	teamID := ctx.Param("id")

	team, err := handler.teams.FindByID(ctx.Request.Context(), teamID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if team.OwnerID != userID {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}

	members, err := handler.members.ListMembers(ctx.Request.Context(), teamID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if members == nil {
		members = []*domain.TeamMember{}
	}

	ctx.JSON(http.StatusOK, gin.H{"items": members})
}

// UpdateTeamMemberRole godoc: PATCH /teams/:id/members/:user_id
func (handler *TeamMemberHandler) UpdateTeamMemberRole(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	teamID := ctx.Param("id")
	targetUserID := ctx.Param("user_id")

	var req struct {
		Role string `json:"role"`
	}
	if err := ctx.ShouldBindJSON(&req); err != nil {
		ctx.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}
	if !domain.ValidTeamRoles[req.Role] {
		ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "role must be admin or member", nil))
		return
	}

	team, err := handler.teams.FindByID(ctx.Request.Context(), teamID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if team.OwnerID != userID {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}
	if targetUserID == team.OwnerID {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "cannot change owner role", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	member, err := handler.members.UpdateRole(ctx.Request.Context(), tx, teamID, targetUserID, req.Role)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "member not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update member", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.team.member.updated", map[string]string{
		"team_id": teamID,
		"user_id": targetUserID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, member)
}

// RemoveTeamMember godoc: DELETE /teams/:id/members/:user_id
func (handler *TeamMemberHandler) RemoveTeamMember(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	teamID := ctx.Param("id")
	targetUserID := ctx.Param("user_id")

	team, err := handler.teams.FindByID(ctx.Request.Context(), teamID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if team.OwnerID != userID {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "team not found", nil))
		return
	}
	if targetUserID == team.OwnerID {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "cannot remove team owner", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := handler.members.RemoveMember(ctx.Request.Context(), tx, teamID, targetUserID); errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "member not found", nil))
		return
	} else if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to remove member", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.team.member.removed", map[string]string{
		"team_id": teamID,
		"user_id": targetUserID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.Status(http.StatusNoContent)
}
