package grpc

import (
	"context"
	"log/slog"
	"runtime/debug"

	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/metadata"
	"google.golang.org/grpc/status"
)

const requestIDKey = "x-request-id"

// NewServer creates a gRPC server with request_id propagation, logging, and panic recovery.
func NewServer(logger *slog.Logger, opts ...grpc.ServerOption) *grpc.Server {
	baseOpts := []grpc.ServerOption{
		grpc.ChainUnaryInterceptor(
			requestIDServerInterceptor(),
			loggingServerInterceptor(logger),
			recoveryServerInterceptor(logger),
		),
	}
	return grpc.NewServer(append(baseOpts, opts...)...)
}

func requestIDServerInterceptor() grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, _ *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		if md, ok := metadata.FromIncomingContext(ctx); ok {
			if vals := md.Get(requestIDKey); len(vals) > 0 {
				ctx = metadata.AppendToOutgoingContext(ctx, requestIDKey, vals[0])
			}
		}
		return handler(ctx, req)
	}
}

func loggingServerInterceptor(logger *slog.Logger) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		resp, err := handler(ctx, req)
		if err != nil {
			logger.Error("grpc call failed", "method", info.FullMethod, "error", err)
		} else {
			logger.Info("grpc call", "method", info.FullMethod)
		}
		return resp, err
	}
}

func recoveryServerInterceptor(logger *slog.Logger) grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, info *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (resp any, err error) {
		defer func() {
			if r := recover(); r != nil {
				logger.Error("grpc panic", "method", info.FullMethod, "panic", r, "stack", string(debug.Stack()))
				err = status.Errorf(codes.Internal, "internal server error")
			}
		}()
		return handler(ctx, req)
	}
}
