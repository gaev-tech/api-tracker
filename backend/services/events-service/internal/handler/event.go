package handler

import (
	"net/http"
	"strings"

	"github.com/gaev-tech/api-tracker/events-service/internal/domain"
	"github.com/gaev-tech/api-tracker/events-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/events-service/internal/store"
	"github.com/gin-gonic/gin"
)

// EventHandler handles event read endpoints.
type EventHandler struct {
	events *store.EventStore
}

// NewEventHandler creates a new EventHandler.
func NewEventHandler(events *store.EventStore) *EventHandler {
	return &EventHandler{events: events}
}

// ListEvents godoc: GET /events
func (h *EventHandler) ListEvents(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)

	params := &domain.EventListParams{
		UserID: userID,
		Filter: ctx.Query("filter"),
		Cursor: ctx.Query("cursor"),
		Limit:  parseLimit(ctx, 50, 100),
	}

	result, err := h.events.List(ctx.Request.Context(), params)
	if err != nil {
		if strings.Contains(err.Error(), "invalid filter") || strings.Contains(err.Error(), "rsql:") {
			ctx.JSON(http.StatusBadRequest, apiErr("validation_error", err.Error(), nil))
			return
		}
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, result)
}

// ListProjectEvents godoc: GET /projects/:id/events
func (h *EventHandler) ListProjectEvents(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	projectID := ctx.Param("id")

	params := &domain.EventListParams{
		UserID:    userID,
		Filter:    ctx.Query("filter"),
		ProjectID: projectID,
		Cursor:    ctx.Query("cursor"),
		Limit:     parseLimit(ctx, 50, 100),
	}

	result, err := h.events.List(ctx.Request.Context(), params)
	if err != nil {
		if strings.Contains(err.Error(), "invalid filter") || strings.Contains(err.Error(), "rsql:") {
			ctx.JSON(http.StatusBadRequest, apiErr("validation_error", err.Error(), nil))
			return
		}
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, result)
}

// ListTaskEvents godoc: GET /tasks/:id/events
func (h *EventHandler) ListTaskEvents(ctx *gin.Context) {
	userID := ctx.GetString(middleware.UserIDKey)
	taskID := ctx.Param("id")

	params := &domain.EventListParams{
		UserID: userID,
		Filter: ctx.Query("filter"),
		TaskID: taskID,
		Cursor: ctx.Query("cursor"),
		Limit:  parseLimit(ctx, 50, 100),
	}

	result, err := h.events.List(ctx.Request.Context(), params)
	if err != nil {
		if strings.Contains(err.Error(), "invalid filter") || strings.Contains(err.Error(), "rsql:") {
			ctx.JSON(http.StatusBadRequest, apiErr("validation_error", err.Error(), nil))
			return
		}
		ctx.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	ctx.JSON(http.StatusOK, result)
}
