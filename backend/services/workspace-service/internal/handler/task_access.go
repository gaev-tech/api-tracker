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

type TaskAccessHandler struct {
	accesses *store.TaskAccessStore
	tasks    *store.TaskStore
	db       *sql.DB
}

func NewTaskAccessHandler(accesses *store.TaskAccessStore, tasks *store.TaskStore, db *sql.DB) *TaskAccessHandler {
	return &TaskAccessHandler{accesses: accesses, tasks: tasks, db: db}
}

// ListTaskAccesses godoc: GET /tasks/:id/accesses
func (handler *TaskAccessHandler) ListTaskAccesses(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")

	task, err := handler.tasks.FindByID(ctx.Request.Context(), taskID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if task.AuthorID != userID {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
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

	// Validate exactly one grantee
	if (req.GranteeUserID == nil) == (req.GranteeTeamID == nil) {
		ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "exactly one of grantee_user_id or grantee_team_id is required", nil))
		return
	}

	task, err := handler.tasks.FindByID(ctx.Request.Context(), taskID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if task.AuthorID != userID {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	access, err := handler.accesses.Create(ctx.Request.Context(), tx, taskID, userID, &req)
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
		"access_id":  access.ID,
		"granted_by": userID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusCreated, access)
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

	task, err := handler.tasks.FindByID(ctx.Request.Context(), taskID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if task.AuthorID != userID {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}

	// Verify access belongs to this task
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

	access, err := handler.accesses.Update(ctx.Request.Context(), tx, accessID, &req)
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

	ctx.JSON(http.StatusOK, access)
}

// RevokeTaskAccess godoc: DELETE /tasks/:id/accesses/:access_id
func (handler *TaskAccessHandler) RevokeTaskAccess(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")
	accessID := ctx.Param("access_id")

	task, err := handler.tasks.FindByID(ctx.Request.Context(), taskID)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if task.AuthorID != userID {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}

	// Verify access belongs to this task
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

	// Auto-delete task if no remaining accesses with any right AND no project associations
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
				"task_id":   taskID,
				"author_id": task.AuthorID,
			})
		}
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.Status(http.StatusNoContent)
}
