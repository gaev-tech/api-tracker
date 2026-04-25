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

type InvitationHandler struct {
	invitations *store.InvitationStore
	members     *store.ProjectMemberStore
	teamMembers *store.TeamMemberStore
	projects    *store.ProjectStore
	teams       *store.TeamStore
	db          *sql.DB
	rights      *access.RightsService
}

func NewInvitationHandler(
	invitations *store.InvitationStore,
	members *store.ProjectMemberStore,
	teamMembers *store.TeamMemberStore,
	projects *store.ProjectStore,
	teams *store.TeamStore,
	db *sql.DB,
	rights *access.RightsService,
) *InvitationHandler {
	return &InvitationHandler{
		invitations: invitations,
		members:     members,
		teamMembers: teamMembers,
		projects:    projects,
		teams:       teams,
		db:          db,
		rights:      rights,
	}
}

// --- Project Invitations ---

// CreateProjectInvitation godoc: POST /projects/:id/invitations
func (handler *InvitationHandler) CreateProjectInvitation(ctx *gin.Context) {
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

	var req struct {
		InviteeUserID *string                  `json:"invitee_user_id"`
		InviteeTeamID *string                  `json:"invitee_team_id"`
		Permissions   domain.ProjectPermissions `json:"permissions"`
	}
	if err := ctx.ShouldBindJSON(&req); err != nil {
		ctx.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	// Validate exactly one invitee
	hasUser := req.InviteeUserID != nil && *req.InviteeUserID != ""
	hasTeam := req.InviteeTeamID != nil && *req.InviteeTeamID != ""
	if hasUser == hasTeam {
		ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "exactly one of invitee_user_id or invitee_team_id must be provided", nil))
		return
	}

	// Cannot grant more rights than you have
	if !access.ProjectPermissionsContain(*projectRights, req.Permissions) {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "cannot grant more rights than you have", nil))
		return
	}

	invitationReq := &domain.ProjectInvitation{
		InviteeUserID: req.InviteeUserID,
		InviteeTeamID: req.InviteeTeamID,
		Permissions:   req.Permissions,
	}
	// Normalize: set nil for empty strings
	if !hasUser {
		invitationReq.InviteeUserID = nil
	}
	if !hasTeam {
		invitationReq.InviteeTeamID = nil
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	invitation, err := handler.invitations.CreateProjectInvitation(ctx.Request.Context(), tx, projectID, userID, invitationReq)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to create invitation", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.project.invitation.created", map[string]string{
		"invitation_id": invitation.ID,
		"project_id":    projectID,
		"invited_by":    userID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusCreated, invitation)
}

// ListProjectInvitations godoc: GET /projects/:id/invitations
func (handler *InvitationHandler) ListProjectInvitations(ctx *gin.Context) {
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

	invitations, err := handler.invitations.ListProjectInvitations(ctx.Request.Context(), projectID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if invitations == nil {
		invitations = []*domain.ProjectInvitation{}
	}

	ctx.JSON(http.StatusOK, gin.H{"items": invitations})
}

// DeleteProjectInvitation godoc: DELETE /projects/:id/invitations/:invitation_id
func (handler *InvitationHandler) DeleteProjectInvitation(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	projectID := ctx.Param("id")
	invitationID := ctx.Param("invitation_id")

	projectRights, err := handler.rights.GetProjectRights(ctx.Request.Context(), projectID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !projectRights.ManageMembers {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to manage members", nil))
		return
	}

	// Verify invitation belongs to this project
	invitation, err := handler.invitations.FindProjectInvitation(ctx.Request.Context(), invitationID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if invitation.ProjectID != projectID {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := handler.invitations.DeleteProjectInvitation(ctx.Request.Context(), tx, invitationID); errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	} else if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to delete invitation", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.Status(http.StatusNoContent)
}

// AcceptProjectInvitation godoc: POST /invitations/projects/:invitation_id/accept
func (handler *InvitationHandler) AcceptProjectInvitation(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	invitationID := ctx.Param("invitation_id")

	invitation, err := handler.invitations.FindProjectInvitation(ctx.Request.Context(), invitationID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if invitation.Status != "pending" {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "invitation is not pending", nil))
		return
	}

	// Check caller is the invitee
	if !handler.isProjectInvitee(ctx, invitation, userID) {
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	accepted, err := handler.invitations.AcceptProjectInvitation(ctx.Request.Context(), tx, invitationID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to accept invitation", nil))
		return
	}

	// Add to project members or project team members
	if accepted.InviteeUserID != nil {
		if err := handler.members.AddMember(ctx.Request.Context(), tx, accepted.ProjectID, *accepted.InviteeUserID, accepted.Permissions); err != nil {
			if errors.Is(err, store.ErrConflict) {
				ctx.JSON(http.StatusConflict, apiErr("conflict", "already a member of this project", nil))
				return
			}
			ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to add member", nil))
			return
		}
	} else if accepted.InviteeTeamID != nil {
		if err := handler.members.AddTeamMember(ctx.Request.Context(), tx, accepted.ProjectID, *accepted.InviteeTeamID, accepted.Permissions); err != nil {
			if errors.Is(err, store.ErrConflict) {
				ctx.JSON(http.StatusConflict, apiErr("conflict", "team is already a member of this project", nil))
				return
			}
			ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to add team member", nil))
			return
		}
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.project.invitation.accepted", map[string]string{
		"invitation_id": accepted.ID,
		"project_id":    accepted.ProjectID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, accepted)
}

// DeclineProjectInvitation godoc: POST /invitations/projects/:invitation_id/decline
func (handler *InvitationHandler) DeclineProjectInvitation(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	invitationID := ctx.Param("invitation_id")

	invitation, err := handler.invitations.FindProjectInvitation(ctx.Request.Context(), invitationID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if invitation.Status != "pending" {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "invitation is not pending", nil))
		return
	}

	// Check caller is the invitee
	if !handler.isProjectInvitee(ctx, invitation, userID) {
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := handler.invitations.DeclineProjectInvitation(ctx.Request.Context(), tx, invitationID); errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	} else if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to decline invitation", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.project.invitation.declined", map[string]string{
		"invitation_id": invitation.ID,
		"project_id":    invitation.ProjectID,
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

// isProjectInvitee checks whether the caller is the invitee of a project invitation.
// For user invitations, the caller must be the invitee user.
// For team invitations, the caller must be an admin of the invitee team.
// Returns true if authorized; writes the error response and returns false otherwise.
func (handler *InvitationHandler) isProjectInvitee(ctx *gin.Context, invitation *domain.ProjectInvitation, userID string) bool {
	if invitation.InviteeUserID != nil {
		if *invitation.InviteeUserID != userID {
			ctx.JSON(http.StatusForbidden, apiErr("forbidden", "you are not the invitee", nil))
			return false
		}
		return true
	}

	if invitation.InviteeTeamID != nil {
		isAdmin, err := handler.invitations.IsTeamAdmin(ctx.Request.Context(), *invitation.InviteeTeamID, userID)
		if err != nil {
			ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
			return false
		}
		if !isAdmin {
			ctx.JSON(http.StatusForbidden, apiErr("forbidden", "only team admins can accept team invitations", nil))
			return false
		}
		return true
	}

	ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "invitation has no invitee", nil))
	return false
}

// --- Team Invitations ---

// CreateTeamInvitation godoc: POST /teams/:id/invitations
func (handler *InvitationHandler) CreateTeamInvitation(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	teamID := ctx.Param("id")

	// Owner-only check
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

	var req struct {
		InviteeUserID string `json:"invitee_user_id"`
	}
	if err := ctx.ShouldBindJSON(&req); err != nil {
		ctx.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}
	if req.InviteeUserID == "" {
		ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "invitee_user_id is required", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	invitation, err := handler.invitations.CreateTeamInvitation(ctx.Request.Context(), tx, teamID, userID, req.InviteeUserID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to create invitation", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.team.invitation.created", map[string]string{
		"invitation_id": invitation.ID,
		"team_id":       teamID,
		"invited_by":    userID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusCreated, invitation)
}

// ListTeamInvitations godoc: GET /teams/:id/invitations
func (handler *InvitationHandler) ListTeamInvitations(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	teamID := ctx.Param("id")

	// Owner-only check
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

	invitations, err := handler.invitations.ListTeamInvitations(ctx.Request.Context(), teamID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if invitations == nil {
		invitations = []*domain.TeamInvitation{}
	}

	ctx.JSON(http.StatusOK, gin.H{"items": invitations})
}

// DeleteTeamInvitation godoc: DELETE /teams/:id/invitations/:invitation_id
func (handler *InvitationHandler) DeleteTeamInvitation(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	teamID := ctx.Param("id")
	invitationID := ctx.Param("invitation_id")

	// Owner-only check
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

	// Verify invitation belongs to this team
	invitation, err := handler.invitations.FindTeamInvitation(ctx.Request.Context(), invitationID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if invitation.TeamID != teamID {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := handler.invitations.DeleteTeamInvitation(ctx.Request.Context(), tx, invitationID); errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	} else if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to delete invitation", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.Status(http.StatusNoContent)
}

// AcceptTeamInvitation godoc: POST /invitations/teams/:invitation_id/accept
func (handler *InvitationHandler) AcceptTeamInvitation(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	invitationID := ctx.Param("invitation_id")

	invitation, err := handler.invitations.FindTeamInvitation(ctx.Request.Context(), invitationID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if invitation.Status != "pending" {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "invitation is not pending", nil))
		return
	}
	if invitation.InviteeUserID != userID {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "you are not the invitee", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	accepted, err := handler.invitations.AcceptTeamInvitation(ctx.Request.Context(), tx, invitationID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to accept invitation", nil))
		return
	}

	// Add user to team as member
	if err := handler.teamMembers.AddMember(ctx.Request.Context(), tx, accepted.TeamID, accepted.InviteeUserID, domain.TeamRoleMember); err != nil {
		if errors.Is(err, store.ErrConflict) {
			ctx.JSON(http.StatusConflict, apiErr("conflict", "already a member of this team", nil))
			return
		}
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to add team member", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.team.invitation.accepted", map[string]string{
		"invitation_id": accepted.ID,
		"team_id":       accepted.TeamID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, accepted)
}

// DeclineTeamInvitation godoc: POST /invitations/teams/:invitation_id/decline
func (handler *InvitationHandler) DeclineTeamInvitation(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	invitationID := ctx.Param("invitation_id")

	invitation, err := handler.invitations.FindTeamInvitation(ctx.Request.Context(), invitationID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if invitation.Status != "pending" {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "invitation is not pending", nil))
		return
	}
	if invitation.InviteeUserID != userID {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "you are not the invitee", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := handler.invitations.DeclineTeamInvitation(ctx.Request.Context(), tx, invitationID); errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "invitation not found", nil))
		return
	} else if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to decline invitation", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.team.invitation.declined", map[string]string{
		"invitation_id": invitation.ID,
		"team_id":       invitation.TeamID,
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
