package handler

import (
	"database/sql"
	"errors"
	"net/http"
	"strings"

	billingv1 "github.com/gaev-tech/api-tracker/contracts/proto/billing/v1"
	"github.com/gaev-tech/api-tracker/backend/pkg/outbox"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/domain"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/store"
	"github.com/gin-gonic/gin"
)

type TaskHandler struct {
	tasks   *store.TaskStore
	db      *sql.DB
	billing billingv1.BillingServiceClient
}

func NewTaskHandler(tasks *store.TaskStore, db *sql.DB, billing billingv1.BillingServiceClient) *TaskHandler {
	return &TaskHandler{tasks: tasks, db: db, billing: billing}
}

// CreateTask godoc: POST /tasks
func (h *TaskHandler) CreateTask(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)

	var req domain.CreateTaskRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}
	req.Title = strings.TrimSpace(req.Title)
	if req.Title == "" {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", "title is required", nil))
		return
	}
	if req.Status != "" && !domain.ValidStatuses[req.Status] {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", "status must be opened, progress, or closed", nil))
		return
	}

	// Check tariff limit
	if h.billing != nil {
		resp, err := h.billing.CheckLimit(c.Request.Context(), &billingv1.CheckLimitRequest{
			UserId:     uid,
			EntityType: billingv1.EntityType_ENTITY_TYPE_TASK,
		})
		if err == nil && !resp.Allowed {
			c.JSON(http.StatusUnprocessableEntity, apiErr("tariff_limit_exceeded", "task limit exceeded for your tariff plan", nil))
			return
		}
	}

	tx, err := h.db.BeginTx(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	task, err := h.tasks.Create(c.Request.Context(), tx, uid, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to create task", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "workspace_outbox", "workspace.task.created", map[string]string{
		"task_id":   task.ID,
		"author_id": uid,
	}); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusCreated, task)
}

// GetTask godoc: GET /tasks/:id
func (h *TaskHandler) GetTask(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	taskID := c.Param("id")

	task, err := h.tasks.FindByID(c.Request.Context(), taskID)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	// For now, only author can see their tasks (full access model in API-31)
	if task.AuthorID != uid {
		c.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}

	c.JSON(http.StatusOK, task)
}

// ListTasks godoc: GET /tasks
func (h *TaskHandler) ListTasks(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)

	sortField, sortDir := parseSort(c, "created_at", "asc")
	params := &domain.TaskListParams{
		AuthorID:  uid,
		Filter:    c.Query("filter"),
		Cursor:    c.Query("cursor"),
		Limit:     parseLimit(c, 50, 100),
		SortField: sortField,
		SortDir:   sortDir,
	}

	result, err := h.tasks.List(c.Request.Context(), params)
	if err != nil {
		if strings.Contains(err.Error(), "invalid filter") {
			c.JSON(http.StatusBadRequest, apiErr("validation_error", err.Error(), nil))
			return
		}
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusOK, result)
}

// UpdateTask godoc: PATCH /tasks/:id
func (h *TaskHandler) UpdateTask(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	taskID := c.Param("id")

	var req domain.UpdateTaskRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	if req.Title != nil {
		trimmed := strings.TrimSpace(*req.Title)
		if trimmed == "" {
			c.JSON(http.StatusBadRequest, apiErr("validation_error", "title cannot be empty", nil))
			return
		}
		req.Title = &trimmed
	}
	if req.Status != nil && !domain.ValidStatuses[*req.Status] {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", "status must be opened, progress, or closed", nil))
		return
	}

	// Verify ownership
	existing, err := h.tasks.FindByID(c.Request.Context(), taskID)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if existing.AuthorID != uid {
		c.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}

	tx, err := h.db.BeginTx(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	task, err := h.tasks.Update(c.Request.Context(), tx, taskID, &req)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update task", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "workspace_outbox", "workspace.task.updated", map[string]string{
		"task_id":   task.ID,
		"author_id": uid,
	}); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusOK, task)
}

// DeleteTask godoc: DELETE /tasks/:id
func (h *TaskHandler) DeleteTask(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	taskID := c.Param("id")

	// Verify ownership
	existing, err := h.tasks.FindByID(c.Request.Context(), taskID)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if existing.AuthorID != uid {
		c.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}

	tx, err := h.db.BeginTx(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := h.tasks.Delete(c.Request.Context(), tx, taskID); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to delete task", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "workspace_outbox", "workspace.task.deleted", map[string]string{
		"task_id":   taskID,
		"author_id": uid,
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

// AttachProject godoc: POST /tasks/:id/projects
func (h *TaskHandler) AttachProject(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	taskID := c.Param("id")

	var req struct {
		ProjectID string `json:"project_id"`
	}
	if err := c.ShouldBindJSON(&req); err != nil || req.ProjectID == "" {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", "project_id is required", nil))
		return
	}

	// Verify ownership
	existing, err := h.tasks.FindByID(c.Request.Context(), taskID)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if existing.AuthorID != uid {
		c.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}

	if err := h.tasks.AttachProject(c.Request.Context(), taskID, req.ProjectID); errors.Is(err, store.ErrConflict) {
		c.JSON(http.StatusConflict, apiErr("conflict", "task already attached to this project", nil))
		return
	} else if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to attach project", nil))
		return
	}

	c.Status(http.StatusNoContent)
}

// DetachProject godoc: DELETE /tasks/:id/projects/:project_id
func (h *TaskHandler) DetachProject(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	taskID := c.Param("id")
	projectID := c.Param("project_id")

	// Verify ownership
	existing, err := h.tasks.FindByID(c.Request.Context(), taskID)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if existing.AuthorID != uid {
		c.JSON(http.StatusNotFound, apiErr("not_found", "task not found", nil))
		return
	}

	if err := h.tasks.DetachProject(c.Request.Context(), taskID, projectID); errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "project association not found", nil))
		return
	} else if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to detach project", nil))
		return
	}

	c.Status(http.StatusNoContent)
}
