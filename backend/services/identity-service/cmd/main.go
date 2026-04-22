package main

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gaev-tech/api-tracker/backend/pkg/logging"
	"github.com/gaev-tech/api-tracker/backend/pkg/sentry"
	identityinternal "github.com/gaev-tech/api-tracker/backend/services/identity-service/internal"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/auth"
	migrationsfs "github.com/gaev-tech/api-tracker/backend/services/identity-service/migrations"
	_ "github.com/lib/pq"
	"github.com/pressly/goose/v3"
)

func main() {
	port := envOr("PORT", "8080")
	dbHost := envOr("DB_HOST", "postgres-identity-rw")
	dbPort := envOr("DB_PORT", "5432")
	dbUser := envOr("DB_USER", "identity_user")
	dbPassword := mustEnv("DB_PASSWORD")
	dbName := envOr("DB_NAME", "identity_db")
	databaseURL := fmt.Sprintf("host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
		dbHost, dbPort, dbUser, dbPassword, dbName,
	)
	jwtPrivateKey := mustEnv("JWT_PRIVATE_KEY")
	jwtIssuer := envOr("JWT_ISSUER", "api-tracker")
	sentryDSN := envOr("SENTRY_DSN", "")

	logger := logging.New("identity")

	if err := sentry.Init(sentryDSN); err != nil {
		logger.Error("sentry init failed", "error", err)
	}

	db, err := sql.Open("postgres", databaseURL)
	if err != nil {
		logger.Error("db open failed", "error", err)
		os.Exit(1)
	}
	defer db.Close()

	if err := runMigrations(db, logger); err != nil {
		logger.Error("migrations failed", "error", err)
		os.Exit(1)
	}

	jwtSvc, err := auth.NewService(jwtPrivateKey, jwtIssuer)
	if err != nil {
		logger.Error("jwt service init failed", "error", err)
		os.Exit(1)
	}

	router := identityinternal.NewRouter(logger, db, jwtSvc)

	srv := &http.Server{
		Addr:    fmt.Sprintf(":%s", port),
		Handler: router,
	}

	go func() {
		logger.Info("starting identity service", "port", port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("server error", "error", err)
			os.Exit(1)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("shutting down")
	shutCtx, shutCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer shutCancel()

	if err := srv.Shutdown(shutCtx); err != nil {
		logger.Error("shutdown error", "error", err)
	}
	logger.Info("stopped")
}

func runMigrations(db *sql.DB, logger *slog.Logger) error {
	goose.SetLogger(goose.NopLogger())
	if err := goose.SetDialect("postgres"); err != nil {
		return err
	}
	goose.SetBaseFS(migrationsfs.FS)
	logger.Info("running migrations")
	return goose.Up(db, ".")
}

func mustEnv(key string) string {
	v := os.Getenv(key)
	if v == "" {
		fmt.Fprintf(os.Stderr, "required env var %s is not set\n", key)
		os.Exit(1)
	}
	return v
}

func envOr(key, defaultVal string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return defaultVal
}
