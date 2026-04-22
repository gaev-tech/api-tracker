package main

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	kafkapkg "github.com/gaev-tech/api-tracker/backend/pkg/kafka"
	"github.com/gaev-tech/api-tracker/backend/pkg/logging"
	"github.com/gaev-tech/api-tracker/backend/pkg/outbox"
	"github.com/gaev-tech/api-tracker/backend/pkg/sentry"
	pinginternal "github.com/gaev-tech/api-tracker/backend/services/ping/internal"
	_ "github.com/lib/pq"
	"github.com/pressly/goose/v3"
)

func main() {
	port := envOr("PORT", "8080")
	databaseURL := mustEnv("DATABASE_URL")
	kafkaBrokers := mustEnv("KAFKA_BROKERS")
	sentryDSN := envOr("SENTRY_DSN", "")

	logger := logging.New("ping")

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

	brokers := strings.Split(kafkaBrokers, ",")
	writer := kafkapkg.NewMultiWriter(brokers)
	defer writer.Close() //nolint:errcheck

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	relay := outbox.New(db, writer, "ping_outbox", logger)
	go relay.Start(ctx)

	router := pinginternal.NewRouter(logger, db)

	srv := &http.Server{
		Addr:    fmt.Sprintf(":%s", port),
		Handler: router,
	}

	go func() {
		logger.Info("starting ping service", "port", port)
		if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			logger.Error("server error", "error", err)
			os.Exit(1)
		}
	}()

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	logger.Info("shutting down")
	cancel()

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
	dir := "migrations"
	logger.Info("running migrations", "dir", dir)
	return goose.Up(db, dir)
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
