package internal

import (
	"database/sql"
	"log/slog"
	"net/http"

	"github.com/gaev-tech/api-tracker/backend/pkg/logging"
	"github.com/gaev-tech/api-tracker/backend/pkg/metrics"
	"github.com/gaev-tech/api-tracker/events-service/internal/handler"
	"github.com/gaev-tech/api-tracker/events-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/events-service/internal/store"
	"github.com/gin-gonic/gin"
)

func NewRouter(logger *slog.Logger, db *sql.DB, eventStore *store.EventStore) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()

	r.Use(logging.RequestLogger(logger))
	r.Use(metrics.Middleware("events"))
	r.Use(gin.Recovery())

	eventH := handler.NewEventHandler(eventStore)

	r.GET("/healthz", func(c *gin.Context) { c.String(http.StatusOK, "ok") })
	r.GET("/readyz", func(c *gin.Context) {
		if err := db.PingContext(c.Request.Context()); err != nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": err.Error()})
			return
		}
		c.String(http.StatusOK, "ok")
	})
	r.GET("/metrics", gin.WrapH(metrics.Handler()))

	authed := r.Group("/", middleware.RequireAuth())

	authed.GET("/events", eventH.ListEvents)
	authed.GET("/projects/:id/events", eventH.ListProjectEvents)
	authed.GET("/tasks/:id/events", eventH.ListTaskEvents)

	return r
}
