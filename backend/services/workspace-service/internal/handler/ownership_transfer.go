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

type OwnershipTransferHandler struct {
	transfers *store.OwnershipTransferStore
	projects  *store.ProjectStore
	members   *store.ProjectMemberStore
	teams     *store.TeamStore
	db        *sql.DB
}

func NewOwnershipTransferHandler(
	transfers *store.OwnershipTransferStore,
	projects *store.ProjectStore,
	members *store.ProjectMemberStore,
	teams *store.TeamStore,
	db *sql.DB,
) *OwnershipTransferHandler {
	return &OwnershipTransferHandler{
		transfers: transfers,
		projects:  projects,
		members:   members,
		teams:     teams,
		db:        db,
	}
}

// CreateProjectTransfer godoc: POST /projects/:id/ownership-transfers
func (handler *OwnershipTransferHandler) CreateProjectTransfer(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	projectID := ctx.Param("id")

	var req struct {
		ToUserID string `json:"to_user_id"`
	}
	if err := ctx.ShouldBindJSON(&req); err != nil {
		ctx.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}
	if req.ToUserID == "" {
		ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "to_user_id is required", nil))
		return
	}
	if req.ToUserID == userID {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "cannot transfer ownership to yourself", nil))
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
	if project.OwnerID != userID {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "only the project owner can transfer ownership", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	transfer, err := handler.transfers.CreateProjectTransfer(ctx.Request.Context(), tx, projectID, userID, req.ToUserID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to create transfer", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.project.ownership_transfer.created", map[string]string{
		"transfer_id": transfer.ID,
		"project_id":  projectID,
		"from_user_id": userID,
		"to_user_id":   req.ToUserID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusCreated, transfer)
}

// CancelProjectTransfer godoc: DELETE /projects/:id/ownership-transfers/:transfer_id
func (handler *OwnershipTransferHandler) CancelProjectTransfer(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	transferID := ctx.Param("transfer_id")

	transfer, err := handler.transfers.FindProjectTransfer(ctx.Request.Context(), transferID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "transfer not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if transfer.FromUserID != userID {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "only the initiator can cancel the transfer", nil))
		return
	}
	if transfer.Status != "pending" {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "transfer is not pending", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := handler.transfers.DeleteProjectTransfer(ctx.Request.Context(), tx, transferID); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to cancel transfer", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.project.ownership_transfer.cancelled", map[string]string{
		"transfer_id": transferID,
		"project_id":  transfer.ProjectID,
		"from_user_id": transfer.FromUserID,
		"to_user_id":   transfer.ToUserID,
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

// AcceptProjectTransfer godoc: POST /ownership-transfers/projects/:transfer_id/accept
func (handler *OwnershipTransferHandler) AcceptProjectTransfer(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	transferID := ctx.Param("transfer_id")

	transfer, err := handler.transfers.FindProjectTransfer(ctx.Request.Context(), transferID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "transfer not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if transfer.ToUserID != userID {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "only the target user can accept the transfer", nil))
		return
	}
	if transfer.Status != "pending" {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "transfer is not pending", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	acceptedTransfer, err := handler.transfers.AcceptProjectTransfer(ctx.Request.Context(), tx, transferID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to accept transfer", nil))
		return
	}

	// Ensure new owner has full permissions as a project member
	fullPermissions := domain.FullProjectPermissions()
	if err := handler.members.UpsertMember(ctx.Request.Context(), tx, transfer.ProjectID, transfer.ToUserID, fullPermissions); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update new owner permissions", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.project.owner_changed", map[string]string{
		"transfer_id":  transferID,
		"project_id":   transfer.ProjectID,
		"from_user_id": transfer.FromUserID,
		"to_user_id":   transfer.ToUserID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, acceptedTransfer)
}

// DeclineProjectTransfer godoc: POST /ownership-transfers/projects/:transfer_id/decline
func (handler *OwnershipTransferHandler) DeclineProjectTransfer(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	transferID := ctx.Param("transfer_id")

	transfer, err := handler.transfers.FindProjectTransfer(ctx.Request.Context(), transferID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "transfer not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if transfer.ToUserID != userID {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "only the target user can decline the transfer", nil))
		return
	}
	if transfer.Status != "pending" {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "transfer is not pending", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	declinedTransfer, err := handler.transfers.DeclineProjectTransfer(ctx.Request.Context(), tx, transferID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to decline transfer", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.project.ownership_transfer.declined", map[string]string{
		"transfer_id":  transferID,
		"project_id":   transfer.ProjectID,
		"from_user_id": transfer.FromUserID,
		"to_user_id":   transfer.ToUserID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, declinedTransfer)
}

// CreateTeamTransfer godoc: POST /teams/:id/ownership-transfers
func (handler *OwnershipTransferHandler) CreateTeamTransfer(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	teamID := ctx.Param("id")

	var req struct {
		ToUserID string `json:"to_user_id"`
	}
	if err := ctx.ShouldBindJSON(&req); err != nil {
		ctx.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}
	if req.ToUserID == "" {
		ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "to_user_id is required", nil))
		return
	}
	if req.ToUserID == userID {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "cannot transfer ownership to yourself", nil))
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
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "only the team owner can transfer ownership", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	transfer, err := handler.transfers.CreateTeamTransfer(ctx.Request.Context(), tx, teamID, userID, req.ToUserID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to create transfer", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.team.ownership_transfer.created", map[string]string{
		"transfer_id":  transfer.ID,
		"team_id":      teamID,
		"from_user_id": userID,
		"to_user_id":   req.ToUserID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusCreated, transfer)
}

// CancelTeamTransfer godoc: DELETE /teams/:id/ownership-transfers/:transfer_id
func (handler *OwnershipTransferHandler) CancelTeamTransfer(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	transferID := ctx.Param("transfer_id")

	transfer, err := handler.transfers.FindTeamTransfer(ctx.Request.Context(), transferID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "transfer not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if transfer.FromUserID != userID {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "only the initiator can cancel the transfer", nil))
		return
	}
	if transfer.Status != "pending" {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "transfer is not pending", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := handler.transfers.DeleteTeamTransfer(ctx.Request.Context(), tx, transferID); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to cancel transfer", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.team.ownership_transfer.cancelled", map[string]string{
		"transfer_id":  transferID,
		"team_id":      transfer.TeamID,
		"from_user_id": transfer.FromUserID,
		"to_user_id":   transfer.ToUserID,
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

// AcceptTeamTransfer godoc: POST /ownership-transfers/teams/:transfer_id/accept
func (handler *OwnershipTransferHandler) AcceptTeamTransfer(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	transferID := ctx.Param("transfer_id")

	transfer, err := handler.transfers.FindTeamTransfer(ctx.Request.Context(), transferID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "transfer not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if transfer.ToUserID != userID {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "only the target user can accept the transfer", nil))
		return
	}
	if transfer.Status != "pending" {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "transfer is not pending", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	acceptedTransfer, err := handler.transfers.AcceptTeamTransfer(ctx.Request.Context(), tx, transferID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to accept transfer", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.team.owner_changed", map[string]string{
		"transfer_id":  transferID,
		"team_id":      transfer.TeamID,
		"from_user_id": transfer.FromUserID,
		"to_user_id":   transfer.ToUserID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, acceptedTransfer)
}

// DeclineTeamTransfer godoc: POST /ownership-transfers/teams/:transfer_id/decline
func (handler *OwnershipTransferHandler) DeclineTeamTransfer(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	transferID := ctx.Param("transfer_id")

	transfer, err := handler.transfers.FindTeamTransfer(ctx.Request.Context(), transferID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "transfer not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if transfer.ToUserID != userID {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "only the target user can decline the transfer", nil))
		return
	}
	if transfer.Status != "pending" {
		ctx.JSON(http.StatusUnprocessableEntity, apiErr("validation_error", "transfer is not pending", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	declinedTransfer, err := handler.transfers.DeclineTeamTransfer(ctx.Request.Context(), tx, transferID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to decline transfer", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.team.ownership_transfer.declined", map[string]string{
		"transfer_id":  transferID,
		"team_id":      transfer.TeamID,
		"from_user_id": transfer.FromUserID,
		"to_user_id":   transfer.ToUserID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, declinedTransfer)
}
