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

type TaskAccessHandler struct {
	accesses *store.TaskAccessStore
	tasks    *store.TaskStore
	db       *sql.DB
	rights   *access.RightsService
}

func NewTaskAccessHandler(accesses *store.TaskAccessStore, tasks *store.TaskStore, db *sql.DB, rights *access.RightsService) *TaskAccessHandler {
	return &TaskAccessHandler{accesses: accesses, tasks: tasks, db: db, rights: rights}
}

// ListTaskAccesses godoc: GET /tasks/:id/accesses
func (handler *TaskAccessHandler) ListTaskAccesses(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")

	taskRights, err := handler.rights.GetTaskRights(ctx.Request.Context(), taskID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !taskRights.Share {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no share permission on this task", nil))
		return
	}

	accesses, err := handler.accesses.ListByTask(ctx.Request.Context(), taskID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if accesses == nil {
		accesses = []*domain.TaskDirectAccess{}
	}

	ctx.JSON(http.StatusOK, gin.H{"items": accesses})
}

// GrantTaskAccess godoc: POST /tasks/:id/accesses
func (handler *TaskAccessHandler) GrantTaskAccess(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")

	var req domain.CreateTaskAccessRequest
	if err := ctx.ShouldBindJSON(&req); err != nil {
		ctx.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	if (req.GranteeUserID == nil) == (req.GranteeTeamID == nil) {
		ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "exactly one of grantee_user_id or grantee_team_id is required", nil))
		return
	}

	taskRights, err := handler.rights.GetTaskRights(ctx.Request.Context(), taskID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !taskRights.Share {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no share permission on this task", nil))
		return
	}
	if !access.TaskPermissionsContain(*taskRights, req.Permissions) {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "cannot grant more rights than you have", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	taskAccess, err := handler.accesses.Create(ctx.Request.Context(), tx, taskID, userID, &req)
	if errors.Is(err, store.ErrConflict) {
		ctx.JSON(http.StatusConflict, apiErr("conflict", "access already exists for this grantee", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to grant access", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.task.access.granted", map[string]string{
		"task_id":    taskID,
		"access_id":  taskAccess.ID,
		"granted_by": userID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusCreated, taskAccess)
}

// UpdateTaskAccess godoc: PATCH /tasks/:id/accesses/:access_id
func (handler *TaskAccessHandler) UpdateTaskAccess(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")
	accessID := ctx.Param("access_id")

	var req domain.UpdateTaskAccessRequest
	if err := ctx.ShouldBindJSON(&req); err != nil {
		ctx.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	taskRights, err := handler.rights.GetTaskRights(ctx.Request.Context(), taskID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !taskRights.Share {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no share permission on this task", nil))
		return
	}
	if !access.TaskPermissionsContain(*taskRights, req.Permissions) {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "cannot grant more rights than you have", nil))
		return
	}

	existing, err := handler.accesses.FindByID(ctx.Request.Context(), accessID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "access not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if existing.TaskID != taskID {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "access not found", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	taskAccess, err := handler.accesses.Update(ctx.Request.Context(), tx, accessID, &req)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "access not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update access", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.task.access.updated", map[string]string{
		"task_id":   taskID,
		"access_id": accessID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, taskAccess)
}

// RevokeTaskAccess godoc: DELETE /tasks/:id/accesses/:access_id
func (handler *TaskAccessHandler) RevokeTaskAccess(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")
	accessID := ctx.Param("access_id")

	taskRights, err := handler.rights.GetTaskRights(ctx.Request.Context(), taskID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !taskRights.Share {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no share permission on this task", nil))
		return
	}

	existing, err := handler.accesses.FindByID(ctx.Request.Context(), accessID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "access not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if existing.TaskID != taskID {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "access not found", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := handler.accesses.Delete(ctx.Request.Context(), tx, accessID); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to revoke access", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.task.access.revoked", map[string]string{
		"task_id":   taskID,
		"access_id": accessID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	// Auto-delete task if no remaining accesses and no project associations
	hasAccess, err := handler.accesses.HasAnyAccess(ctx.Request.Context(), tx, taskID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !hasAccess {
		var projectCount int
		if err := tx.QueryRowContext(ctx.Request.Context(), `SELECT COUNT(*) FROM task_projects WHERE task_id = $1`, taskID).Scan(&projectCount); err != nil {
			ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
			return
		}
		if projectCount == 0 {
			if err := handler.tasks.Delete(ctx.Request.Context(), tx, taskID); err != nil {
				ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to auto-delete task", nil))
				return
			}
			_ = outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.task.deleted", map[string]string{
				"task_id": taskID,
			})
		}
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.Status(http.StatusNoContent)
}
