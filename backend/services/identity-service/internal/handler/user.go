package handler

import (
	"database/sql"
	"errors"
	"net/http"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/gaev-tech/api-tracker/backend/pkg/outbox"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/domain"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/store"
	"github.com/gin-gonic/gin"
)

type UserHandler struct {
	users *store.UserStore
	db    *sql.DB
}

func NewUserHandler(users *store.UserStore, db *sql.DB) *UserHandler {
	return &UserHandler{users: users, db: db}
}

// GetMe godoc: GET /users/me
func (h *UserHandler) GetMe(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	user, err := h.users.FindByID(c.Request.Context(), uid)
	if errors.Is(err, store.ErrNotFound) {
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
		Name     *string `json:"name"`
		Theme    string  `json:"theme"`
		Language string  `json:"language"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	// Fetch current values to use as defaults
	current, err := h.users.FindByID(c.Request.Context(), uid)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusUnauthorized, apiErr("unauthorized", "user not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	name := current.Name
	if req.Name != nil {
		name = strings.TrimSpace(*req.Name)
		if utf8.RuneCountInString(name) > 100 {
			c.JSON(http.StatusBadRequest, apiErr("validation_error", "name must be at most 100 characters", nil))
			return
		}
	}
	theme := current.Theme
	if req.Theme != "" {
		theme = req.Theme
	}
	language := current.Language
	if req.Language != "" {
		language = req.Language
	}

	updated, err := h.users.UpdateProfile(c.Request.Context(), uid, name, theme, language)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update profile", nil))
		return
	}
	c.JSON(http.StatusOK, updated)
}

// DeleteMe godoc: DELETE /users/me
func (h *UserHandler) DeleteMe(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)

	var req struct {
		ConfirmationEmail string `json:"confirmation_email"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}
	if req.ConfirmationEmail == "" {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", "confirmation_email is required", nil))
		return
	}

	user, err := h.users.FindByID(c.Request.Context(), uid)
	if errors.Is(err, store.ErrNotFound) {
		c.JSON(http.StatusUnauthorized, apiErr("unauthorized", "user not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	if !strings.EqualFold(req.ConfirmationEmail, user.Email) {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", "confirmation_email does not match your email", nil))
		return
	}

	tx, err := h.db.BeginTx(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := h.users.Delete(c.Request.Context(), tx, uid); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to delete account", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "identity_outbox", "identity.user.deleted", map[string]string{
		"user_id": uid,
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

// SearchUsers godoc: GET /users/search
func (h *UserHandler) SearchUsers(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)

	q := strings.TrimSpace(c.Query("q"))
	if utf8.RuneCountInString(q) < 2 {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", "q must be at least 2 characters", nil))
		return
	}

	limit := 20
	if l := c.Query("limit"); l != "" {
		parsed, err := strconv.Atoi(l)
		if err != nil || parsed < 1 {
			c.JSON(http.StatusBadRequest, apiErr("validation_error", "limit must be a positive integer", nil))
			return
		}
		limit = parsed
	}
	if limit > 50 {
		limit = 50
	}

	results, err := h.users.SearchByEmail(c.Request.Context(), uid, q, limit)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if results == nil {
		results = make([]*domain.UserSearchResult, 0)
	}

	c.JSON(http.StatusOK, gin.H{"items": results})
}
