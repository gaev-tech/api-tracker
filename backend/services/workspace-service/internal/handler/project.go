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

type ProjectHandler struct {
	projects *store.ProjectStore
	members  *store.ProjectMemberStore
	db       *sql.DB
}

func NewProjectHandler(projects *store.ProjectStore, members *store.ProjectMemberStore, db *sql.DB) *ProjectHandler {
	return &ProjectHandler{projects: projects, members: members, db: db}
}

// CreateProject godoc: POST /projects
func (h *ProjectHandler) CreateProject(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)

	var req domain.CreateProjectRequest
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

	project, err := h.projects.Create(c.Request.Context(), tx, uid, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to create project", nil))
		return
	}

	// Add owner as member with full permissions
	if err := h.members.AddMember(c.Request.Context(), tx, project.ID, uid, domain.FullProjectPermissions()); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to add owner as member", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "workspace_outbox", "workspace.project.created", map[string]string{
		"project_id": project.ID,
		"owner_id":   uid,
	}); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusCreated, project)
}

// ListProjects godoc: GET /projects
func (h *ProjectHandler) ListProjects(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)

	params := &domain.ProjectListParams{
		OwnerID: uid,
		Cursor:  c.Query("cursor"),
		Limit:   parseLimit(c, 50, 100),
	}

	result, err := h.projects.ListByOwner(c.Request.Context(), params)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusOK, result)
}

// GetProject godoc: GET /projects/:id
func (h *ProjectHandler) GetProject(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	projectID := c.Param("id")

	project, err := h.projects.FindByID(c.Request.Context(), projectID)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "project not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	if project.OwnerID != uid {
		c.JSON(http.StatusNotFound, apiErr("not_found", "project not found", nil))
		return
	}

	c.JSON(http.StatusOK, project)
}

// UpdateProject godoc: PATCH /projects/:id
func (h *ProjectHandler) UpdateProject(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	projectID := c.Param("id")

	var req domain.UpdateProjectRequest
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
	existing, err := h.projects.FindByID(c.Request.Context(), projectID)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "project not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if existing.OwnerID != uid {
		c.JSON(http.StatusNotFound, apiErr("not_found", "project not found", nil))
		return
	}

	tx, err := h.db.BeginTx(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	project, err := h.projects.Update(c.Request.Context(), tx, projectID, &req)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "project not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update project", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "workspace_outbox", "workspace.project.updated", map[string]string{
		"project_id": project.ID,
		"owner_id":   uid,
	}); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusOK, project)
}

// DeleteProject godoc: DELETE /projects/:id
func (h *ProjectHandler) DeleteProject(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	projectID := c.Param("id")

	// Verify ownership
	existing, err := h.projects.FindByID(c.Request.Context(), projectID)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusNotFound, apiErr("not_found", "project not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if existing.OwnerID != uid {
		c.JSON(http.StatusNotFound, apiErr("not_found", "project not found", nil))
		return
	}

	tx, err := h.db.BeginTx(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := h.projects.Delete(c.Request.Context(), tx, projectID); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to delete project", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "workspace_outbox", "workspace.project.deleted", map[string]string{
		"project_id": projectID,
		"owner_id":   uid,
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
