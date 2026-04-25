package handler

import (
	"database/sql"
	"errors"
	"net/http"

	"github.com/gaev-tech/api-tracker/backend/pkg/outbox"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/access"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/store"
	"github.com/gin-gonic/gin"
)

type ProjectMemberHandler struct {
	members  *store.ProjectMemberStore
	projects *store.ProjectStore
	db       *sql.DB
	rights   *access.RightsService
}

func NewProjectMemberHandler(members *store.ProjectMemberStore, projects *store.ProjectStore, db *sql.DB, rights *access.RightsService) *ProjectMemberHandler {
	return &ProjectMemberHandler{members: members, projects: projects, db: db, rights: rights}
}

// ListMembers godoc: GET /projects/:id/members
func (handler *ProjectMemberHandler) ListMembers(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	projectID := ctx.Param("id")

	projectRights, err := handler.rights.GetProjectRights(ctx.Request.Context(), projectID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !projectRights.ManageMembers {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to manage members", nil))
		return
	}

	members, err := handler.members.ListMembers(ctx.Request.Context(), projectID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if members == nil {
		members = []*domain.ProjectMember{}
	}

	ctx.JSON(http.StatusOK, gin.H{"items": members})
}

// UpdateMember godoc: PATCH /projects/:id/members/:user_id
func (handler *ProjectMemberHandler) UpdateMember(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	projectID := ctx.Param("id")
	targetUserID := ctx.Param("user_id")

	var req struct {
		Permissions domain.ProjectPermissions `json:"permissions"`
	}
	if err := ctx.ShouldBindJSON(&req); err != nil {
		ctx.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	projectRights, err := handler.rights.GetProjectRights(ctx.Request.Context(), projectID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !projectRights.ManageMembers {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to manage members", nil))
		return
	}
	if !access.ProjectPermissionsContain(*projectRights, req.Permissions) {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "cannot grant more rights than you have", nil))
		return
	}

	project, err := handler.projects.FindByID(ctx.Request.Context(), projectID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "project not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if targetUserID == project.OwnerID {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "cannot modify owner permissions", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	member, err := handler.members.UpdateMember(ctx.Request.Context(), tx, projectID, targetUserID, req.Permissions)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "member not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update member", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.project.member.updated", map[string]string{
		"project_id": projectID,
		"user_id":    targetUserID,
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

// RemoveMember godoc: DELETE /projects/:id/members/:user_id
func (handler *ProjectMemberHandler) RemoveMember(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	projectID := ctx.Param("id")
	targetUserID := ctx.Param("user_id")

	projectRights, err := handler.rights.GetProjectRights(ctx.Request.Context(), projectID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !projectRights.ManageMembers {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to manage members", nil))
		return
	}

	project, err := handler.projects.FindByID(ctx.Request.Context(), projectID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "project not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if targetUserID == project.OwnerID {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "cannot remove project owner", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := handler.members.RemoveMember(ctx.Request.Context(), tx, projectID, targetUserID); errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "member not found", nil))
		return
	} else if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to remove member", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.project.member.removed", map[string]string{
		"project_id": projectID,
		"user_id":    targetUserID,
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

// ListTeamMembers godoc: GET /projects/:id/team-members
func (handler *ProjectMemberHandler) ListTeamMembers(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	projectID := ctx.Param("id")

	projectRights, err := handler.rights.GetProjectRights(ctx.Request.Context(), projectID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !projectRights.ManageMembers {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to manage members", nil))
		return
	}

	members, err := handler.members.ListTeamMembers(ctx.Request.Context(), projectID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if members == nil {
		members = []*domain.ProjectTeamMember{}
	}

	ctx.JSON(http.StatusOK, gin.H{"items": members})
}

// UpdateTeamMember godoc: PATCH /projects/:id/team-members/:team_id
func (handler *ProjectMemberHandler) UpdateTeamMember(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	projectID := ctx.Param("id")
	teamID := ctx.Param("team_id")

	var req struct {
		Permissions domain.ProjectPermissions `json:"permissions"`
	}
	if err := ctx.ShouldBindJSON(&req); err != nil {
		ctx.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	projectRights, err := handler.rights.GetProjectRights(ctx.Request.Context(), projectID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !projectRights.ManageMembers {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to manage members", nil))
		return
	}
	if !access.ProjectPermissionsContain(*projectRights, req.Permissions) {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "cannot grant more rights than you have", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	member, err := handler.members.UpdateTeamMember(ctx.Request.Context(), tx, projectID, teamID, req.Permissions)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "team member not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update team member", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.project.team_member.updated", map[string]string{
		"project_id": projectID,
		"team_id":    teamID,
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

// RemoveTeamMember godoc: DELETE /projects/:id/team-members/:team_id
func (handler *ProjectMemberHandler) RemoveTeamMember(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	projectID := ctx.Param("id")
	teamID := ctx.Param("team_id")

	projectRights, err := handler.rights.GetProjectRights(ctx.Request.Context(), projectID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !projectRights.ManageMembers {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to manage members", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := handler.members.RemoveTeamMember(ctx.Request.Context(), tx, projectID, teamID); errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "team member not found", nil))
		return
	} else if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to remove team member", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.project.team_member.removed", map[string]string{
		"project_id": projectID,
		"team_id":    teamID,
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
