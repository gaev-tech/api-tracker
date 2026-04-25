package handler

import (
	"database/sql"
	"errors"
	"net/http"
	"strings"

	billingv1 "github.com/gaev-tech/api-tracker/contracts/proto/billing/v1"
	"github.com/gaev-tech/api-tracker/backend/pkg/outbox"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/access"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/store"
	"github.com/gin-gonic/gin"
)

type TaskHandler struct {
	tasks   *store.TaskStore
	db      *sql.DB
	billing billingv1.BillingServiceClient
	rights  *access.RightsService
}

func NewTaskHandler(tasks *store.TaskStore, db *sql.DB, billing billingv1.BillingServiceClient, rights *access.RightsService) *TaskHandler {
	return &TaskHandler{tasks: tasks, db: db, billing: billing, rights: rights}
}

// CreateTask godoc: POST /tasks
func (handler *TaskHandler) CreateTask(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)

	var req domain.CreateTaskRequest
	if err := ctx.ShouldBindJSON(&req); err != nil {
		ctx.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}
	req.Title = strings.TrimSpace(req.Title)
	if req.Title == "" {
		ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "title is required", nil))
		return
	}
	if req.Status != "" && !domain.ValidStatuses[req.Status] {
		ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "status must be opened, progress, or closed", nil))
		return
	}

	// Check tariff limit
	if handler.billing != nil {
		resp, err := handler.billing.CheckLimit(ctx.Request.Context(), &billingv1.CheckLimitRequest{
			UserId:     userID,
			EntityType: billingv1.EntityType_ENTITY_TYPE_TASK,
		})
		if err == nil && !resp.Allowed {
			ctx.JSON(http.StatusUnprocessableEntity, apiErr("tariff_limit_exceeded", "task limit exceeded for your tariff plan", nil))
			return
		}
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	task, err := handler.tasks.Create(ctx.Request.Context(), tx, userID, &req)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to create task", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.task.created", map[string]string{
		"task_id":   task.ID,
		"author_id": userID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusCreated, task)
}

// GetTask godoc: GET /tasks/:id
func (handler *TaskHandler) GetTask(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")

	visible, err := handler.rights.CanSeeTask(ctx.Request.Context(), taskID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !visible {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
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

	ctx.JSON(http.StatusOK, task)
}

// ListTasks godoc: GET /tasks
func (handler *TaskHandler) ListTasks(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)

	sortField, sortDir := parseSort(ctx, "created_at", "asc")
	params := &domain.TaskListParams{
		UserID:    userID,
		Filter:    ctx.Query("filter"),
		Cursor:    ctx.Query("cursor"),
		Limit:     parseLimit(ctx, 50, 100),
		SortField: sortField,
		SortDir:   sortDir,
	}

	result, err := handler.tasks.ListVisible(ctx.Request.Context(), params)
	if err != nil {
		if strings.Contains(err.Error(), "invalid filter") {
			ctx.JSON(http.StatusBadRequest, apiErr("validation_error", err.Error(), nil))
			return
		}
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, result)
}

// UpdateTask godoc: PATCH /tasks/:id
func (handler *TaskHandler) UpdateTask(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")

	var req domain.UpdateTaskRequest
	if err := ctx.ShouldBindJSON(&req); err != nil {
		ctx.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	if req.Title != nil {
		trimmed := strings.TrimSpace(*req.Title)
		if trimmed == "" {
			ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "title cannot be empty", nil))
			return
		}
		req.Title = &trimmed
	}
	if req.Status != nil && !domain.ValidStatuses[*req.Status] {
		ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "status must be opened, progress, or closed", nil))
		return
	}

	// Check per-field rights
	rights, err := handler.rights.GetTaskRights(ctx.Request.Context(), taskID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if req.Title != nil && !rights.EditTitle {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to edit title", nil))
		return
	}
	if req.Description != nil && !rights.EditDescription {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to edit description", nil))
		return
	}
	if req.Status != nil && !rights.EditStatus {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to edit status", nil))
		return
	}
	if req.AssigneeID != nil && !rights.EditAssignee {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to edit assignee", nil))
		return
	}
	if req.Tags != nil && !rights.EditTags {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to edit tags", nil))
		return
	}
	if req.BlockingTaskIDs != nil && !rights.EditBlockers {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to edit blockers", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	task, err := handler.tasks.Update(ctx.Request.Context(), tx, taskID, &req)
	if errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update task", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.task.updated", map[string]string{
		"task_id": task.ID,
	}); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, task)
}

// DeleteTask godoc: DELETE /tasks/:id
func (handler *TaskHandler) DeleteTask(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")

	rights, err := handler.rights.GetTaskRights(ctx.Request.Context(), taskID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !rights.DeleteTask {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to delete task", nil))
		return
	}

	tx, err := handler.db.BeginTx(ctx.Request.Context(), nil)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := handler.tasks.Delete(ctx.Request.Context(), tx, taskID); err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to delete task", nil))
		return
	}

	if err := outbox.Write(ctx.Request.Context(), tx, "workspace_outbox", "workspace.task.deleted", map[string]string{
		"task_id": taskID,
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

// AttachProject godoc: POST /tasks/:id/projects
func (handler *TaskHandler) AttachProject(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")

	var req struct {
		ProjectID string `json:"project_id"`
	}
	if err := ctx.ShouldBindJSON(&req); err != nil || req.ProjectID == "" {
		ctx.JSON(http.StatusBadRequest, apiErr("validation_error", "project_id is required", nil))
		return
	}

	// Check ManageAttachments right in target project
	projectRights, err := handler.rights.GetProjectRights(ctx.Request.Context(), req.ProjectID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !projectRights.ManageAttachments {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to attach tasks to this project", nil))
		return
	}

	if err := handler.tasks.AttachProject(ctx.Request.Context(), taskID, req.ProjectID); errors.Is(err, store.ErrConflict) {
		ctx.JSON(http.StatusConflict, apiErr("conflict", "task already attached to this project", nil))
		return
	} else if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to attach project", nil))
		return
	}

	ctx.Status(http.StatusNoContent)
}

// DetachProject godoc: DELETE /tasks/:id/projects/:project_id
func (handler *TaskHandler) DetachProject(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")
	projectID := ctx.Param("project_id")

	// Check ManageAttachments right in project
	projectRights, err := handler.rights.GetProjectRights(ctx.Request.Context(), projectID, userID)
	if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !projectRights.ManageAttachments {
		ctx.JSON(http.StatusForbidden, apiErr("forbidden", "no permission to detach tasks from this project", nil))
		return
	}

	if err := handler.tasks.DetachProject(ctx.Request.Context(), taskID, projectID); errors.Is(err, store.ErrNotFound) {
		ctx.JSON(http.StatusNotFound, apiErr("not_found", "project association not found", nil))
		return
	} else if err != nil {
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to detach project", nil))
		return
	}

	ctx.Status(http.StatusNoContent)
}
