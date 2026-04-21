package grpc

import (
	"context"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/metadata"
)

const defaultTimeout = 5 * time.Second

// NewClient creates a gRPC client connection with a 5s default timeout and request_id propagation.
// The caller is responsible for closing the connection.
func NewClient(target string, opts ...grpc.DialOption) (*grpc.ClientConn, error) {
	baseOpts := []grpc.DialOption{
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithChainUnaryInterceptor(
			timeoutClientInterceptor(defaultTimeout),
			requestIDClientInterceptor(),
		),
	}
	return grpc.NewClient(target, append(baseOpts, opts...)...)
}

// timeoutClientInterceptor applies a deadline to every outgoing unary call.
func timeoutClientInterceptor(timeout time.Duration) grpc.UnaryClientInterceptor {
	return func(ctx context.Context, method string, req, reply any, cc *grpc.ClientConn, invoker grpc.UnaryInvoker, opts ...grpc.CallOption) error {
		if _, ok := ctx.Deadline(); !ok {
			var cancel context.CancelFunc
			ctx, cancel = context.WithTimeout(ctx, timeout)
			defer cancel()
		}
		return invoker(ctx, method, req, reply, cc, opts...)
	}
}

// requestIDClientInterceptor forwards x-request-id from incoming to outgoing metadata.
func requestIDClientInterceptor() grpc.UnaryClientInterceptor {
	return func(ctx context.Context, method string, req, reply any, cc *grpc.ClientConn, invoker grpc.UnaryInvoker, opts ...grpc.CallOption) error {
		if md, ok := metadata.FromIncomingContext(ctx); ok {
			if vals := md.Get(requestIDKey); len(vals) > 0 {
				ctx = metadata.AppendToOutgoingContext(ctx, requestIDKey, vals[0])
			}
		}
		return invoker(ctx, method, req, reply, cc, opts...)
	}
}
