package handler

import (
	"crypto/rand"
	"crypto/sha256"
	"database/sql"
	"encoding/base64"
	"fmt"
	"net/http"
	"strings"

	"github.com/gaev-tech/api-tracker/backend/pkg/outbox"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/domain"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/store"
	"github.com/gin-gonic/gin"
)

type PATHandler struct {
	pats *store.PATStore
	db   *sql.DB
}

func NewPATHandler(pats *store.PATStore, db *sql.DB) *PATHandler {
	return &PATHandler{pats: pats, db: db}
}

// ListPATs godoc: GET /pats
func (h *PATHandler) ListPATs(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)

	pats, err := h.pats.ListByUser(c.Request.Context(), uid)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if pats == nil {
		pats = make([]*domain.PAT, 0)
	}

	c.JSON(http.StatusOK, gin.H{"items": pats})
}

// GetPAT godoc: GET /pats/:id
func (h *PATHandler) GetPAT(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	patID := c.Param("id")

	pat, err := h.pats.FindByID(c.Request.Context(), uid, patID)
	if err == store.ErrNotFound {
		c.JSON(http.StatusNotFound, apiErr("not_found", "PAT not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusOK, pat)
}

// CreatePAT godoc: POST /pats
func (h *PATHandler) CreatePAT(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)

	var req struct {
		Name string `json:"name"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}
	req.Name = strings.TrimSpace(req.Name)
	if req.Name == "" {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", "name is required", nil))
		return
	}

	rawToken, tokenHash, err := generatePAT()
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to generate token", nil))
		return
	}

	tx, err := h.db.BeginTx(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	pat, err := h.pats.CreateTx(c.Request.Context(), tx, uid, req.Name, tokenHash)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to create PAT", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "identity_outbox", "identity.pat.created", map[string]string{
		"pat_id":  pat.ID,
		"user_id": uid,
	}); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to write outbox", nil))
		return
	}

	if err := tx.Commit(); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	pat.Token = &rawToken
	c.JSON(http.StatusCreated, pat)
}

// UpdatePAT godoc: PATCH /pats/:id
func (h *PATHandler) UpdatePAT(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	patID := c.Param("id")

	var req struct {
		Name string `json:"name"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}
	req.Name = strings.TrimSpace(req.Name)
	if req.Name == "" {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", "name is required", nil))
		return
	}

	pat, err := h.pats.UpdateName(c.Request.Context(), uid, patID, req.Name)
	if err == store.ErrNotFound {
		c.JSON(http.StatusNotFound, apiErr("not_found", "PAT not found or already revoked", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusOK, pat)
}

// RevokePAT godoc: DELETE /pats/:id
func (h *PATHandler) RevokePAT(c *gin.Context) {
	uid := c.GetString(middleware.UserIDKey)
	patID := c.Param("id")

	tx, err := h.db.BeginTx(c.Request.Context(), nil)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	defer tx.Rollback()

	if err := h.pats.RevokeTx(c.Request.Context(), tx, uid, patID); err == store.ErrNotFound {
		c.JSON(http.StatusNotFound, apiErr("not_found", "PAT not found or already revoked", nil))
		return
	} else if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	if err := outbox.Write(c.Request.Context(), tx, "identity_outbox", "identity.pat.revoked", map[string]string{
		"pat_id":  patID,
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

// generatePAT creates a raw PAT string (pat_ + 32 random bytes base64url) and its SHA-256 hash.
func generatePAT() (raw, hash string, err error) {
	b := make([]byte, 32)
	if _, err = rand.Read(b); err != nil {
		return "", "", err
	}
	raw = "pat_" + base64.RawURLEncoding.EncodeToString(b)
	sum := sha256.Sum256([]byte(raw))
	hash = fmt.Sprintf("%x", sum)
	return raw, hash, nil
}
