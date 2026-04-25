package grpcserver

import (
	"context"

	workspacev1 "github.com/gaev-tech/api-tracker/contracts/proto/workspace/v1"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/access"
	"github.com/gaev-tech/api-tracker/workspace-service/internal/store"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

type Server struct {
	workspacev1.UnimplementedWorkspaceServiceServer
	rights  *access.RightsService
	members *store.ProjectMemberStore
}

func New(rights *access.RightsService, members *store.ProjectMemberStore) *Server {
	return &Server{rights: rights, members: members}
}

// GetTaskRights returns effective rights bitmask for user on task.
func (server *Server) GetTaskRights(ctx context.Context, req *workspacev1.GetTaskRightsRequest) (*workspacev1.GetTaskRightsResponse, error) {
	if req.UserId == "" || req.TaskId == "" {
		return nil, status.Error(codes.InvalidArgument, "user_id and task_id are required")
	}

	permissions, err := server.rights.GetTaskRights(ctx, req.TaskId, req.UserId)
	if err != nil {
		return nil, status.Error(codes.Internal, "failed to compute rights")
	}

	var bitmask uint32
	if permissions.EditTitle {
		bitmask |= 1 << 0
	}
	if permissions.EditDescription {
		bitmask |= 1 << 1
	}
	if permissions.EditTags {
		bitmask |= 1 << 2
	}
	if permissions.EditBlockers {
		bitmask |= 1 << 3
	}
	if permissions.EditAssignee {
		bitmask |= 1 << 4
	}
	if permissions.EditStatus {
		bitmask |= 1 << 5
	}
	if permissions.Share {
		bitmask |= 1 << 6
	}
	if permissions.DeleteTask {
		bitmask |= 1 << 7
	}

	return &workspacev1.GetTaskRightsResponse{Rights: bitmask}, nil
}

// GetProjectMembers returns all members of a project with their roles.
func (server *Server) GetProjectMembers(ctx context.Context, req *workspacev1.GetProjectMembersRequest) (*workspacev1.GetProjectMembersResponse, error) {
	if req.ProjectId == "" {
		return nil, status.Error(codes.InvalidArgument, "project_id is required")
	}

	members, err := server.members.ListMembers(ctx, req.ProjectId)
	if err != nil {
		return nil, status.Error(codes.Internal, "failed to list members")
	}

	var protoMembers []*workspacev1.ProjectMember
	for _, member := range members {
		protoMembers = append(protoMembers, &workspacev1.ProjectMember{
			UserId: member.UserID,
			Role:   "member",
		})
	}

	return &workspacev1.GetProjectMembersResponse{Members: protoMembers}, nil
}
