package middleware

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

const UserIDKey = "user_id"

// RequireAuth reads X-User-Id forwarded by api-gateway.
// events-service does not validate JWT directly — that's identity-service's job.
func RequireAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		uid := c.GetHeader("X-User-Id")
		if uid == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{
				"error": gin.H{"code": "unauthorized", "message": "missing X-User-Id header"},
			})
			return
		}
		c.Set(UserIDKey, uid)
		c.Next()
	}
}
