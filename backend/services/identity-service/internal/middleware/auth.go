package middleware

import (
	"net/http"
	"strings"

	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/auth"
	"github.com/gin-gonic/gin"
)

const UserIDKey = "user_id"

// RequireAuth reads X-User-Id forwarded by api-gateway. Falls back to validating
// the Bearer JWT directly for local development (when api-gateway is not in the path).
func RequireAuth(jwtSvc *auth.Service) gin.HandlerFunc {
	return func(c *gin.Context) {
		if uid := c.GetHeader("X-User-Id"); uid != "" {
			c.Set(UserIDKey, uid)
			c.Next()
			return
		}
		authHeader := c.GetHeader("Authorization")
		if !strings.HasPrefix(authHeader, "Bearer ") {
			c.AbortWithStatusJSON(http.StatusUnauthorized, apiError("unauthorized", "missing or invalid token", nil))
			return
		}
		claims, err := jwtSvc.ParseAccessToken(strings.TrimPrefix(authHeader, "Bearer "))
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, apiError("unauthorized", "invalid token", nil))
			return
		}
		c.Set(UserIDKey, claims.Subject)
		c.Next()
	}
}

func apiError(code, message string, details interface{}) gin.H {
	e := gin.H{"code": code, "message": message}
	if details != nil {
		e["details"] = details
	}
	return gin.H{"error": e}
}
