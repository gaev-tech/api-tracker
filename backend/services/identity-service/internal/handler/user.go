package handler

import (
	"net/http"

	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/store"
	"github.com/gin-gonic/gin"
)

type UserHandler struct {
	users *store.UserStore
}

func NewUserHandler(users *store.UserStore) *UserHandler {
	return &UserHandler{users: users}
}

// GetMe godoc: GET /users/me
func (h *UserHandler) GetMe(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	user, err := h.users.FindByID(c.Request.Context(), uid)
	if err == store.ErrNotFound {
		c.JSON(http.StatusUnauthorized, apiErr("unauthorized", "user not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	c.JSON(http.StatusOK, user)
}

// PatchMe godoc: PATCH /users/me
func (h *UserHandler) PatchMe(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)

	var req struct {
		Theme    string `json:"theme"`
		Language string `json:"language"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	// Fetch current values to use as defaults
	current, err := h.users.FindByID(c.Request.Context(), uid)
	if err == store.ErrNotFound {
		c.JSON(http.StatusUnauthorized, apiErr("unauthorized", "user not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	theme := current.Theme
	if req.Theme != "" {
		theme = req.Theme
	}
	language := current.Language
	if req.Language != "" {
		language = req.Language
	}

	updated, err := h.users.UpdateProfile(c.Request.Context(), uid, theme, language)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update profile", nil))
		return
	}
	c.JSON(http.StatusOK, updated)
}
