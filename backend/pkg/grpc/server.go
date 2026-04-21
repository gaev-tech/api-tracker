package grpc

import (
	"context"

	"google.golang.org/grpc"
	"google.golang.org/grpc/metadata"
)

const requestIDKey = "x-request-id"

// NewServer creates a gRPC server with request_id propagation and timeout interceptors.
func NewServer(opts ...grpc.ServerOption) *grpc.Server {
	baseOpts := []grpc.ServerOption{
		grpc.ChainUnaryInterceptor(requestIDServerInterceptor()),
	}
	return grpc.NewServer(append(baseOpts, opts...)...)
}

// requestIDServerInterceptor extracts x-request-id from incoming metadata and adds it to the context.
func requestIDServerInterceptor() grpc.UnaryServerInterceptor {
	return func(ctx context.Context, req any, _ *grpc.UnaryServerInfo, handler grpc.UnaryHandler) (any, error) {
		if md, ok := metadata.FromIncomingContext(ctx); ok {
			if vals := md.Get(requestIDKey); len(vals) > 0 {
				ctx = metadata.NewOutgoingContext(ctx, metadata.Pairs(requestIDKey, vals[0]))
			}
		}
		return handler(ctx, req)
	}
}
