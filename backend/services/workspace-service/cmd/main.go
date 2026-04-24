package main

import (
	"context"
	"database/sql"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	billingv1 "github.com/gaev-tech/api-tracker/contracts/proto/billing/v1"
	workspacev1 "github.com/gaev-tech/api-tracker/contracts/proto/workspace/v1"
	grpcpkg "github.com/gaev-tech/api-tracker/backend/pkg/grpc"
	kafkapkg "github.com/gaev-tech/api-tracker/backend/pkg/kafka"
	"github.com/gaev-tech/api-tracker/backend/pkg/logging"
	"github.com/gaev-tech/api-tracker/backend/pkg/outbox"
	"github.com/gaev-tech/api-tracker/backend/pkg/sentry"
	workspaceinternal "github.com/gaev-tech/api-tracker/workspace-service/internal"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/consumer"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/grpcserver"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/store"
	migrationsfs "github.com/gaev-tech/api-tracker/workspace-service/migrations"
	_ "github.com/lib/pq"
	"github.com/pressly/goose/v3"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	port := envOr("PORT", "8080")
	dbHost := envOr("DB_HOST", "citus-coordinator")
	dbPort := envOr("DB_PORT", "5432")
	dbUser := envOr("DB_USER", "workspace_user")
	dbPassword := mustEnv("DB_PASSWORD")
	dbName := envOr("DB_NAME", "workspace_db")
	databaseURL := fmt.Sprintf("host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
		dbHost, dbPort, dbUser, dbPassword, dbName,
	)
	sentryDSN := envOr("SENTRY_DSN", "")
	kafkaBrokers := envOr("KAFKA_BROKERS", "kafka-cluster-kafka-bootstrap.kafka.svc:9092")
	grpcPort := envOr("GRPC_PORT", "9090")
	billingAddr := envOr("BILLING_GRPC_ADDR", "billing-service:9090")

	logger := logging.New("workspace")

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

	// Billing gRPC client
	var billingClient billingv1.BillingServiceClient
	billingConn, err := grpc.NewClient(billingAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		logger.Warn("billing gRPC connection failed, limit checks disabled", "error", err)
	} else {
		defer billingConn.Close()
		billingClient = billingv1.NewBillingServiceClient(billingConn)
		logger.Info("billing gRPC client connected", "addr", billingAddr)
	}

	router := workspaceinternal.NewRouter(logger, db, billingClient)

	// Outbox relay for Kafka events
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	brokers := strings.Split(kafkaBrokers, ",")
	kafkaWriter := kafkapkg.NewMultiWriter(brokers)
	defer kafkaWriter.Close()

	relay := outbox.New(db, kafkaWriter, "workspace_outbox", logger)
	go relay.Start(ctx)

	// Kafka consumer for identity events → users_cache
	userCacheStore := store.NewUserCacheStore(db)
	identityConsumer := consumer.NewIdentityConsumer(brokers, userCacheStore, logger)
	go identityConsumer.Start(ctx)

	// gRPC server
	grpcSrv := grpcpkg.NewServer(logger)
	workspacev1.RegisterWorkspaceServiceServer(grpcSrv, grpcserver.New())

	grpcLis, err := net.Listen("tcp", fmt.Sprintf(":%s", grpcPort))
	if err != nil {
		logger.Error("grpc listen failed", "error", err)
		os.Exit(1)
	}
	go func() {
		logger.Info("starting gRPC server", "port", grpcPort)
		if err := grpcSrv.Serve(grpcLis); err != nil {
			logger.Error("grpc server error", "error", err)
			os.Exit(1)
		}
	}()

	// HTTP server
	srv := &http.Server{
		Addr:    fmt.Sprintf(":%s", port),
		Handler: router,
	}

	go func() {
		logger.Info("starting workspace service", "port", port)
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
	grpcSrv.GracefulStop()

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
