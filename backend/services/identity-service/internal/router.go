package internal

import (
	"database/sql"
	"log/slog"
	"net/http"

	"github.com/gaev-tech/api-tracker/backend/pkg/logging"
	"github.com/gaev-tech/api-tracker/backend/pkg/metrics"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/auth"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/handler"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/store"
	"github.com/gin-gonic/gin"
)

func NewRouter(logger *slog.Logger, db *sql.DB, jwtSvc *auth.Service) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()

	r.Use(logging.RequestLogger(logger))
	r.Use(metrics.Middleware("identity"))
	r.Use(gin.Recovery())

	userStore := store.NewUserStore(db)
	refreshStore := store.NewRefreshTokenStore(db)

	authH := handler.NewAuthHandler(userStore, refreshStore, jwtSvc)
	userH := handler.NewUserHandler(userStore)

	r.GET("/healthz", func(c *gin.Context) { c.String(http.StatusOK, "ok") })
	r.GET("/readyz", func(c *gin.Context) {
		if err := db.PingContext(c.Request.Context()); err != nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": err.Error()})
			return
		}
		c.String(http.StatusOK, "ok")
	})
	r.GET("/metrics", gin.WrapH(metrics.Handler()))
	r.GET("/.well-known/jwks.json", func(c *gin.Context) {
		c.JSON(http.StatusOK, jwtSvc.JWKS())
	})

	// Public auth endpoints
	authGroup := r.Group("/auth")
	authGroup.POST("/register", authH.Register)
	authGroup.POST("/login", authH.Login)
	authGroup.POST("/refresh", authH.Refresh)
	authGroup.POST("/email/verify", authH.VerifyEmail)

	// Authenticated auth endpoints
	authed := r.Group("/", middleware.RequireAuth(jwtSvc))
	authed.POST("/auth/logout", authH.Logout)
	authed.POST("/auth/password/change", authH.ChangePassword)

	// User endpoints
	authed.GET("/users/me", userH.GetMe)
	authed.PATCH("/users/me", userH.PatchMe)

	return r
}
