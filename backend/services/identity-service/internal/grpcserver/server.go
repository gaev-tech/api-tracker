package grpcserver

import (
	"context"

	identityv1 "github.com/gaev-tech/api-tracker/contracts/proto/identity/v1"
	"github.com/gaev-tech/api-tracker/backend/services/identity-service/internal/store"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type Server struct {
	identityv1.UnimplementedIdentityServiceServer
	pats  *store.PATStore
	users *store.UserStore
}

func New(pats *store.PATStore, users *store.UserStore) *Server {
	return &Server{pats: pats, users: users}
}

func (s *Server) ValidateToken(ctx context.Context, req *identityv1.ValidateTokenRequest) (*identityv1.ValidateTokenResponse, error) {
	if req.Token == "" {
		return nil, status.Error(codes.InvalidArgument, "token is required")
	}

	userID, err := s.pats.FindUserByTokenHash(ctx, hashToken(req.Token))
	if err == store.ErrNotFound {
		return nil, status.Error(codes.Unauthenticated, "invalid or revoked token")
	}
	if err != nil {
		return nil, status.Error(codes.Internal, "database error")
	}

	return &identityv1.ValidateTokenResponse{UserId: userID}, nil
}

func (s *Server) GetUser(ctx context.Context, req *identityv1.GetUserRequest) (*identityv1.GetUserResponse, error) {
	return nil, status.Error(codes.Unimplemented, "GetUser not implemented yet")
}
