package internal

import (
	"database/sql"
	"log/slog"
	"net/http"

	"github.com/gaev-tech/api-tracker/backend/pkg/logging"
	"github.com/gaev-tech/api-tracker/backend/pkg/metrics"
	"github.com/gaev-tech/api-tracker/backend/pkg/outbox"
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
	r.POST("/ping", handlePostPing(db))

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

// handlePostPing writes a ping-events record to the outbox within a transaction.
func handlePostPing(db *sql.DB) gin.HandlerFunc {
	return func(c *gin.Context) {
		tx, err := db.BeginTx(c.Request.Context(), nil)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		defer tx.Rollback() //nolint:errcheck

		if err := outbox.Write(c.Request.Context(), tx, "ping_outbox", "ping-events",
			map[string]string{"status": "pong"},
		); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		if err := tx.Commit(); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}

		c.JSON(http.StatusOK, gin.H{"status": "pong"})
	}
}
