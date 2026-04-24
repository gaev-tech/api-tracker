package internal

import (
	"database/sql"
	"log/slog"
	"net/http"

	billingv1 "github.com/gaev-tech/api-tracker/contracts/proto/billing/v1"
	"github.com/gaev-tech/api-tracker/backend/pkg/logging"
	"github.com/gaev-tech/api-tracker/backend/pkg/metrics"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/handler"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/middleware"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/store"
	"github.com/gin-gonic/gin"
)

func NewRouter(logger *slog.Logger, db *sql.DB, billing billingv1.BillingServiceClient) *gin.Engine {
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()

	r.Use(logging.RequestLogger(logger))
	r.Use(metrics.Middleware("workspace"))
	r.Use(gin.Recovery())

	taskStore := store.NewTaskStore(db)
	taskH := handler.NewTaskHandler(taskStore, db, billing)

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

	// Task endpoints
	authed.POST("/tasks", taskH.CreateTask)
	authed.GET("/tasks", taskH.ListTasks)
	authed.GET("/tasks/:id", taskH.GetTask)
	authed.PATCH("/tasks/:id", taskH.UpdateTask)
	authed.DELETE("/tasks/:id", taskH.DeleteTask)
	authed.POST("/tasks/:id/projects", taskH.AttachProject)
	authed.DELETE("/tasks/:id/projects/:project_id", taskH.DetachProject)

	// Project endpoints
	projectStore := store.NewProjectStore(db)
	projectH := handler.NewProjectHandler(projectStore, db)

	authed.POST("/projects", projectH.CreateProject)
	authed.GET("/projects", projectH.ListProjects)
	authed.GET("/projects/:id", projectH.GetProject)
	authed.PATCH("/projects/:id", projectH.UpdateProject)
	authed.DELETE("/projects/:id", projectH.DeleteProject)

	// Team endpoints
	teamStore := store.NewTeamStore(db)
	teamH := handler.NewTeamHandler(teamStore, db)

	authed.POST("/teams", teamH.CreateTeam)
	authed.GET("/teams", teamH.ListTeams)
	authed.GET("/teams/:id", teamH.GetTeam)
	authed.PATCH("/teams/:id", teamH.UpdateTeam)
	authed.DELETE("/teams/:id", teamH.DeleteTeam)

	return r
}
