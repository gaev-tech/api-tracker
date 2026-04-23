package grpc

import (
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"log/slog"
	"os"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials"
)

const (
	envTLSCert = "GRPC_TLS_CERT_FILE"
	envTLSKey  = "GRPC_TLS_KEY_FILE"
	envTLSCA   = "GRPC_TLS_CA_FILE"
)

// NewServerTLS creates a gRPC server with mTLS.
// certFile and keyFile are the server certificate and private key.
// caFile is the CA certificate used to verify client certificates.
func NewServerTLS(logger *slog.Logger, certFile, keyFile, caFile string, opts ...grpc.ServerOption) (*grpc.Server, error) {
	creds, err := serverTLSCredentials(certFile, keyFile, caFile)
	if err != nil {
		return nil, fmt.Errorf("grpc server TLS: %w", err)
	}
	return NewServer(logger, append([]grpc.ServerOption{grpc.Creds(creds)}, opts...)...), nil
}

// NewClientTLS creates a gRPC client connection with mTLS.
// certFile and keyFile are the client certificate and private key.
// caFile is the CA certificate used to verify the server certificate.
func NewClientTLS(target, certFile, keyFile, caFile string, opts ...grpc.DialOption) (*grpc.ClientConn, error) {
	creds, err := clientTLSCredentials(certFile, keyFile, caFile)
	if err != nil {
		return nil, fmt.Errorf("grpc client TLS: %w", err)
	}
	return NewClient(target, append([]grpc.DialOption{grpc.WithTransportCredentials(creds)}, opts...)...)
}

// NewServerFromEnv creates a gRPC server reading TLS config from env vars
// (GRPC_TLS_CERT_FILE, GRPC_TLS_KEY_FILE, GRPC_TLS_CA_FILE).
// Falls back to insecure if none are set (useful for local development).
func NewServerFromEnv(logger *slog.Logger, opts ...grpc.ServerOption) (*grpc.Server, error) {
	cert, key, ca := os.Getenv(envTLSCert), os.Getenv(envTLSKey), os.Getenv(envTLSCA)
	if cert == "" && key == "" && ca == "" {
		logger.Warn("grpc server: TLS env vars not set, using insecure transport")
		return NewServer(logger, opts...), nil
	}
	return NewServerTLS(logger, cert, key, ca, opts...)
}

// NewClientFromEnv creates a gRPC client connection reading TLS config from env vars.
// Falls back to insecure if none are set.
func NewClientFromEnv(target string, logger *slog.Logger, opts ...grpc.DialOption) (*grpc.ClientConn, error) {
	cert, key, ca := os.Getenv(envTLSCert), os.Getenv(envTLSKey), os.Getenv(envTLSCA)
	if cert == "" && key == "" && ca == "" {
		logger.Warn("grpc client: TLS env vars not set, using insecure transport", "target", target)
		return NewClient(target, opts...)
	}
	// Strip the WithTransportCredentials(insecure) that NewClient adds by default,
	// since we provide our own credentials via prepended DialOption.
	tlsCreds, err := clientTLSCredentials(cert, key, ca)
	if err != nil {
		return nil, fmt.Errorf("grpc client TLS: %w", err)
	}
	allOpts := append([]grpc.DialOption{grpc.WithTransportCredentials(tlsCreds)}, opts...)
	return grpc.NewClient(target, append(baseClientOpts(), allOpts...)...)
}

// baseClientOpts returns the interceptor options shared by NewClient and NewClientFromEnv,
// without the transport credentials (those are set per-call).
func baseClientOpts() []grpc.DialOption {
	return []grpc.DialOption{
		grpc.WithChainUnaryInterceptor(
			timeoutClientInterceptor(defaultTimeout),
			requestIDClientInterceptor(),
		),
	}
}

func serverTLSCredentials(certFile, keyFile, caFile string) (credentials.TransportCredentials, error) {
	cert, err := tls.LoadX509KeyPair(certFile, keyFile)
	if err != nil {
		return nil, fmt.Errorf("load server cert/key: %w", err)
	}
	ca, err := loadCACert(caFile)
	if err != nil {
		return nil, err
	}
	return credentials.NewTLS(&tls.Config{
		Certificates: []tls.Certificate{cert},
		ClientCAs:    ca,
		ClientAuth:   tls.RequireAndVerifyClientCert,
		MinVersion:   tls.VersionTLS13,
	}), nil
}

func clientTLSCredentials(certFile, keyFile, caFile string) (credentials.TransportCredentials, error) {
	cert, err := tls.LoadX509KeyPair(certFile, keyFile)
	if err != nil {
		return nil, fmt.Errorf("load client cert/key: %w", err)
	}
	ca, err := loadCACert(caFile)
	if err != nil {
		return nil, err
	}
	return credentials.NewTLS(&tls.Config{
		Certificates: []tls.Certificate{cert},
		RootCAs:      ca,
		MinVersion:   tls.VersionTLS13,
	}), nil
}

func loadCACert(caFile string) (*x509.CertPool, error) {
	caPEM, err := os.ReadFile(caFile)
	if err != nil {
		return nil, fmt.Errorf("read CA cert: %w", err)
	}
	pool := x509.NewCertPool()
	if !pool.AppendCertsFromPEM(caPEM) {
		return nil, fmt.Errorf("parse CA cert: no valid certificates found in %s", caFile)
	}
	return pool, nil
}
