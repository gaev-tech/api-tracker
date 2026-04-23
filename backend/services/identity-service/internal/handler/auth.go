package handler

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"strings"
	"unicode/utf8"

	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/auth"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/store"
	"github.com/gin-gonic/gin"
	"golang.org/x/crypto/bcrypt"
)

type AuthHandler struct {
	users         *store.UserStore
	refreshTokens *store.RefreshTokenStore
	jwtSvc        *auth.Service
}

func NewAuthHandler(users *store.UserStore, refreshTokens *store.RefreshTokenStore, jwtSvc *auth.Service) *AuthHandler {
	return &AuthHandler{users: users, refreshTokens: refreshTokens, jwtSvc: jwtSvc}
}

// Register godoc: POST /auth/register
func (h *AuthHandler) Register(c *gin.Context) {
	var req struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}
	req.Email = strings.TrimSpace(req.Email)
	if err := validateCredentials(req.Email, req.Password); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", err.Error(), nil))
		return
	}

	passwordHash, err := bcrypt.GenerateFromPassword([]byte(req.Password), 12)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to hash password", nil))
		return
	}

	verificationToken, err := generateVerificationToken()
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to generate token", nil))
		return
	}

	user, err := h.users.Create(c.Request.Context(), req.Email, string(passwordHash), verificationToken)
	if err == store.ErrConflict {
		c.JSON(http.StatusConflict, apiErr("conflict", "email already taken", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to create user", nil))
		return
	}

	// TODO: replace with real email delivery when email service is available.
	// For now the token is logged so it can be used in local/staging environments.
	fmt.Printf("[identity] email verification token for %s: %s\n", user.Email, verificationToken)

	c.JSON(http.StatusCreated, gin.H{"user": user})
}

// VerifyEmail godoc: POST /auth/email/verify
func (h *AuthHandler) VerifyEmail(c *gin.Context) {
	var req struct {
		Token string `json:"token"`
	}
	if err := c.ShouldBindJSON(&req); err != nil || req.Token == "" {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "token required", nil))
		return
	}

	user, err := h.users.VerifyEmail(c.Request.Context(), req.Token)
	if err == store.ErrNotFound {
		c.JSON(http.StatusUnprocessableEntity, apiErr("invalid_token", "verification token is invalid or already used", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	c.JSON(http.StatusOK, gin.H{"user": user})
}

// Login godoc: POST /auth/login
func (h *AuthHandler) Login(c *gin.Context) {
	var req struct {
		Email    string `json:"email"`
		Password string `json:"password"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	user, passwordHash, err := h.users.FindByEmail(c.Request.Context(), req.Email)
	if err == store.ErrNotFound {
		c.JSON(http.StatusUnauthorized, apiErr("unauthorized", "invalid credentials", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if !user.IsActive {
		c.JSON(http.StatusUnauthorized, apiErr("unauthorized", "account deactivated", nil))
		return
	}
	if user.EmailVerifiedAt == nil {
		c.JSON(http.StatusUnauthorized, apiErr("unauthorized", "email not verified", nil))
		return
	}
	if err := bcrypt.CompareHashAndPassword([]byte(passwordHash), []byte(req.Password)); err != nil {
		c.JSON(http.StatusUnauthorized, apiErr("unauthorized", "invalid credentials", nil))
		return
	}

	accessToken, refreshToken, err := h.issueTokenPair(c, user.ID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to issue tokens", nil))
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"access_token":  accessToken,
		"refresh_token": refreshToken,
	})
}

// Refresh godoc: POST /auth/refresh
func (h *AuthHandler) Refresh(c *gin.Context) {
	var req struct {
		RefreshToken string `json:"refresh_token"`
	}
	if err := c.ShouldBindJSON(&req); err != nil || req.RefreshToken == "" {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "refresh_token required", nil))
		return
	}

	tokenHash := hashToken(req.RefreshToken)
	userID, err := h.refreshTokens.FindByHash(c.Request.Context(), tokenHash)
	if err == store.ErrNotFound {
		c.JSON(http.StatusUnauthorized, apiErr("unauthorized", "refresh token invalid or expired", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}

	// Rotate: revoke old token
	if err := h.refreshTokens.Revoke(c.Request.Context(), tokenHash); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to revoke token", nil))
		return
	}

	accessToken, newRefreshToken, err := h.issueTokenPair(c, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to issue tokens", nil))
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"access_token":  accessToken,
		"refresh_token": newRefreshToken,
	})
}

// Logout godoc: POST /auth/logout
func (h *AuthHandler) Logout(c *gin.Context) {
	var req struct {
		RefreshToken string `json:"refresh_token"`
	}
	// Body is optional
	_ = c.ShouldBindJSON(&req)

	if req.RefreshToken != "" {
		tokenHash := hashToken(req.RefreshToken)
		_ = h.refreshTokens.Revoke(c.Request.Context(), tokenHash)
	} else {
		// Revoke all sessions for the authenticated user
		userID, _ := c.Get(middleware.UserIDKey)
		if uid, ok := userID.(string); ok && uid != "" {
			_ = h.refreshTokens.RevokeAllForUser(c.Request.Context(), uid)
		}
	}

	c.Status(http.StatusNoContent)
}

// ChangePassword godoc: POST /auth/password/change
func (h *AuthHandler) ChangePassword(c *gin.Context) {
	userID, _ := c.Get(middleware.UserIDKey)
	uid, _ := userID.(string)

	var req struct {
		CurrentPassword string `json:"current_password"`
		NewPassword     string `json:"new_password"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "invalid JSON", nil))
		return
	}

	currentHash, err := h.users.GetPasswordHash(c.Request.Context(), uid)
	if err == store.ErrNotFound {
		c.JSON(http.StatusUnauthorized, apiErr("unauthorized", "user not found", nil))
		return
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "database error", nil))
		return
	}
	if err := bcrypt.CompareHashAndPassword([]byte(currentHash), []byte(req.CurrentPassword)); err != nil {
		c.JSON(http.StatusUnauthorized, apiErr("unauthorized", "current password incorrect", nil))
		return
	}
	if err := validatePassword(req.NewPassword); err != nil {
		c.JSON(http.StatusBadRequest, apiErr("validation_error", err.Error(), nil))
		return
	}

	newHash, err := bcrypt.GenerateFromPassword([]byte(req.NewPassword), 12)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to hash password", nil))
		return
	}
	if err := h.users.UpdatePassword(c.Request.Context(), uid, string(newHash)); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to update password", nil))
		return
	}

	// Revoke all refresh tokens (force re-login everywhere)
	_ = h.refreshTokens.RevokeAllForUser(c.Request.Context(), uid)

	c.Status(http.StatusNoContent)
}

// issueTokenPair creates a new access + refresh token pair and stores the refresh token hash.
func (h *AuthHandler) issueTokenPair(c *gin.Context, userID string) (accessToken, refreshToken string, err error) {
	accessToken, err = h.jwtSvc.GenerateAccessToken(userID)
	if err != nil {
		return
	}
	var tokenHash string
	refreshToken, tokenHash, err = auth.GenerateRefreshToken()
	if err != nil {
		return
	}
	err = h.refreshTokens.Create(c.Request.Context(), userID, tokenHash, auth.RefreshTokenExpiry())
	return
}

func validateCredentials(email, password string) error {
	if !strings.Contains(email, "@") || len(email) < 3 {
		return fmt.Errorf("invalid email format")
	}
	return validatePassword(password)
}

func validatePassword(password string) error {
	if utf8.RuneCountInString(password) < 8 {
		return fmt.Errorf("password must be at least 8 characters")
	}
	return nil
}

func hashToken(token string) string {
	sum := sha256.Sum256([]byte(token))
	return fmt.Sprintf("%x", sum)
}

func apiErr(code, message string, details interface{}) gin.H {
	e := gin.H{"code": code, "message": message}
	if details != nil {
		e["details"] = details
	}
	return gin.H{"error": e}
}

func generateVerificationToken() (string, error) {
	b := make([]byte, 32)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}
