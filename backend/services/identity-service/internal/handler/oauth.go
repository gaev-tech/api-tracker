package handler

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"net/http"
	"strings"
	"time"

	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/auth"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/store"
	"github.com/gin-gonic/gin"
)

const authCodeTTL = 10 * time.Minute

type OAuthHandler struct {
	oauthStore    *store.OAuthStore
	refreshTokens *store.RefreshTokenStore
	pats          *store.PATStore
	users         *store.UserStore
	jwtSvc        *auth.Service
}

func NewOAuthHandler(oauthStore *store.OAuthStore, refreshTokens *store.RefreshTokenStore, pats *store.PATStore, users *store.UserStore, jwtSvc *auth.Service) *OAuthHandler {
	return &OAuthHandler{
		oauthStore:    oauthStore,
		refreshTokens: refreshTokens,
		pats:          pats,
		users:         users,
		jwtSvc:        jwtSvc,
	}
}

// Authorize handles GET /oauth/authorize — requires authenticated user.
func (h *OAuthHandler) Authorize(c *gin.Context) {
	responseType := c.Query("response_type")
	clientID := c.Query("client_id")
	redirectURI := c.Query("redirect_uri")
	codeChallenge := c.Query("code_challenge")
	codeChallengeMethod := c.Query("code_challenge_method")
	state := c.Query("state")

	if responseType != "code" {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "response_type must be 'code'", nil))
		return
	}
	if clientID == "" || redirectURI == "" {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "client_id and redirect_uri are required", nil))
		return
	}
	if codeChallenge != "" && codeChallengeMethod != "S256" {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "code_challenge_method must be 'S256'", nil))
		return
	}

	allowedURIs, err := h.oauthStore.FindClient(c.Request.Context(), clientID)
	if err != nil {
		c.JSON(http.StatusBadRequest, apiErr("invalid_client", "unknown client_id", nil))
		return
	}

	if !matchRedirectURI(redirectURI, allowedURIs, clientID) {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "redirect_uri not allowed", nil))
		return
	}

	userID, _ := c.Get(middleware.UserIDKey)
	uid, _ := userID.(string)

	codeBytes := make([]byte, 32)
	if _, err := rand.Read(codeBytes); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to generate code", nil))
		return
	}
	code := hex.EncodeToString(codeBytes)
	codeHash := hashToken(code)

	expiresAt := time.Now().Add(authCodeTTL)
	if err := h.oauthStore.CreateAuthCode(c.Request.Context(), codeHash, clientID, uid, redirectURI, codeChallenge, expiresAt); err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to store authorization code", nil))
		return
	}

	location := redirectURI + "?code=" + code
	if state != "" {
		location += "&state=" + state
	}

	// JSON clients (e.g. SPA) cannot follow 302 and read Location header,
	// so return the redirect URL in a JSON body when Accept: application/json.
	if strings.Contains(c.GetHeader("Accept"), "application/json") {
		c.JSON(http.StatusOK, gin.H{"redirect_url": location})
		return
	}
	c.Redirect(http.StatusFound, location)
}

// Token handles POST /oauth/token — public endpoint.
func (h *OAuthHandler) Token(c *gin.Context) {
	grantType := formOrJSON(c, "grant_type")

	switch grantType {
	case "authorization_code":
		h.tokenAuthorizationCode(c)
	case "refresh_token":
		h.tokenRefreshToken(c)
	default:
		c.JSON(http.StatusBadRequest, apiErr("unsupported_grant_type", "grant_type must be 'authorization_code' or 'refresh_token'", nil))
	}
}

func (h *OAuthHandler) tokenAuthorizationCode(c *gin.Context) {
	code := formOrJSON(c, "code")
	redirectURI := formOrJSON(c, "redirect_uri")
	clientID := formOrJSON(c, "client_id")
	codeVerifier := formOrJSON(c, "code_verifier")

	if code == "" || redirectURI == "" || clientID == "" {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "code, redirect_uri, and client_id are required", nil))
		return
	}

	codeHash := hashToken(code)
	storedClientID, userID, storedRedirectURI, storedCodeChallenge, err := h.oauthStore.ExchangeAuthCode(c.Request.Context(), codeHash)
	if err != nil {
		c.JSON(http.StatusBadRequest, apiErr("invalid_grant", "authorization code is invalid, expired, or already used", nil))
		return
	}

	if storedClientID != clientID {
		c.JSON(http.StatusBadRequest, apiErr("invalid_grant", "client_id mismatch", nil))
		return
	}
	if storedRedirectURI != redirectURI {
		c.JSON(http.StatusBadRequest, apiErr("invalid_grant", "redirect_uri mismatch", nil))
		return
	}

	// PKCE verification
	if storedCodeChallenge != "" {
		if codeVerifier == "" {
			c.JSON(http.StatusBadRequest, apiErr("invalid_grant", "code_verifier is required", nil))
			return
		}
		computed := computeS256Challenge(codeVerifier)
		if computed != storedCodeChallenge {
			c.JSON(http.StatusBadRequest, apiErr("invalid_grant", "code_verifier does not match code_challenge", nil))
			return
		}
	}

	accessToken, refreshToken, err := h.issueTokenPair(c, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, apiErr("internal_error", "failed to issue tokens", nil))
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"access_token":  accessToken,
		"refresh_token": refreshToken,
		"token_type":    "bearer",
		"expires_in":    int(auth.AccessTokenTTL.Seconds()),
	})
}

func (h *OAuthHandler) tokenRefreshToken(c *gin.Context) {
	refreshToken := formOrJSON(c, "refresh_token")
	if refreshToken == "" {
		c.JSON(http.StatusBadRequest, apiErr("bad_request", "refresh_token is required", nil))
		return
	}

	tokenHash := hashToken(refreshToken)
	userID, err := h.refreshTokens.FindByHash(c.Request.Context(), tokenHash)
	if err != nil {
		c.JSON(http.StatusUnauthorized, apiErr("invalid_grant", "refresh token invalid or expired", nil))
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
		"token_type":    "bearer",
		"expires_in":    int(auth.AccessTokenTTL.Seconds()),
	})
}

func (h *OAuthHandler) issueTokenPair(c *gin.Context, userID string) (accessToken, refreshToken string, err error) {
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

// matchRedirectURI checks if the given URI is allowed.
// For the "cli" client, prefix match on "http://localhost" is used (any port).
func matchRedirectURI(uri string, allowed []string, clientID string) bool {
	for _, a := range allowed {
		if clientID == "cli" && strings.HasPrefix(uri, a) {
			return true
		}
		if uri == a {
			return true
		}
	}
	return false
}

// computeS256Challenge computes base64url(sha256(verifier)) without padding.
func computeS256Challenge(verifier string) string {
	sum := sha256.Sum256([]byte(verifier))
	return base64.RawURLEncoding.EncodeToString(sum[:])
}

// formOrJSON reads a field from form-urlencoded data or falls back to JSON body.
func formOrJSON(c *gin.Context, key string) string {
	if v := c.PostForm(key); v != "" {
		return v
	}
	// Try JSON body — gin caches the body after first bind, so we use a map.
	var body map[string]string
	if err := c.ShouldBindJSON(&body); err == nil {
		return body[key]
	}
	return ""
}

// ValidateToken handles POST /auth/validate — called by nginx auth_request.
func (h *OAuthHandler) ValidateToken(c *gin.Context) {
	authHeader := c.GetHeader("Authorization")
	if !strings.HasPrefix(authHeader, "Bearer ") {
		c.Status(http.StatusUnauthorized)
		return
	}
	token := strings.TrimPrefix(authHeader, "Bearer ")

	var userID string

	if strings.HasPrefix(token, "pat_") {
		// PAT validation
		uid, err := h.pats.FindUserByTokenHash(c.Request.Context(), hashToken(token))
		if err != nil {
			c.Status(http.StatusUnauthorized)
			return
		}
		userID = uid
	} else {
		// JWT validation
		claims, err := h.jwtSvc.ParseAccessToken(token)
		if err != nil {
			c.Status(http.StatusUnauthorized)
			return
		}
		userID = claims.Subject
	}

	user, err := h.users.FindByID(c.Request.Context(), userID)
	if err != nil {
		c.Status(http.StatusUnauthorized)
		return
	}

	parentUserID := ""
	if user.ParentUserID != nil {
		parentUserID = *user.ParentUserID
	}
	isActive := "false"
	if user.IsActive {
		isActive = "true"
	}

	c.Header("X-User-Id", user.ID)
	c.Header("X-Parent-User-Id", parentUserID)
	c.Header("X-Is-Active", isActive)
	c.Status(http.StatusOK)
}
