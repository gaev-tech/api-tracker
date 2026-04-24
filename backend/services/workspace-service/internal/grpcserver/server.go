package grpcserver

import (
	"context"

	workspacev1 "github.com/gaev-tech/api-tracker/contracts/proto/workspace/v1"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type Server struct {
	workspacev1.UnimplementedWorkspaceServiceServer
}

func New() *Server {
	return &Server{}
}

// GetTaskRights returns effective rights bitmask for user on task.
// TODO: API-35 — implement full rights calculation
func (s *Server) GetTaskRights(ctx context.Context, req *workspacev1.GetTaskRightsRequest) (*workspacev1.GetTaskRightsResponse, error) {
	return nil, status.Error(codes.Unimplemented, "GetTaskRights not implemented yet")
}

// GetProjectMembers returns all members of a project.
// TODO: API-35 — implement after project members are added
func (s *Server) GetProjectMembers(ctx context.Context, req *workspacev1.GetProjectMembersRequest) (*workspacev1.GetProjectMembersResponse, error) {
	return nil, status.Error(codes.Unimplemented, "GetProjectMembers not implemented yet")
}
