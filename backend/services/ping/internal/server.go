package internal

import (
	"database/sql"
	"log/slog"
	"net/http"

	"github.com/gaev-tech/api-tracker/backend/pkg/logging"
	"github.com/gaev-tech/api-tracker/backend/pkg/metrics"
	"github.com/gin-gonic/gin"
)

// NewRouter builds and returns the Gin router for the ping service.
func NewRouter(logger *slog.Logger, db *sql.DB) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()

	r.Use(logging.RequestLogger(logger))
	r.Use(metrics.Middleware("ping"))
	r.Use(gin.Recovery())

	r.GET("/healthz", handleHealthz)
	r.GET("/readyz", handleReadyz(db))
	r.GET("/metrics", gin.WrapH(metrics.Handler()))

	return r
}

func handleHealthz(c *gin.Context) {
	c.String(http.StatusOK, "ok")
}

func handleReadyz(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		if err := db.PingContext(c.Request.Context()); err != nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": err.Error()})
			return
		}
		c.String(http.StatusOK, "ok")
	}
}
