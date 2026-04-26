package ws

import (
	"encoding/json"
	"log/slog"

	"github.com/gaev-tech/api-tracker/events-service/internal/domain"
)

// invitationTopics lists event types that should trigger an invitation update notification.
var invitationTopics = map[string]struct{}{
	"workspace.project.invitation.created":  {},
	"workspace.project.invitation.accepted": {},
	"workspace.project.invitation.declined": {},
	"workspace.team.invitation.created":     {},
	"workspace.team.invitation.accepted":    {},
	"workspace.team.invitation.declined":    {},
}

// InvitationNotifier watches for invitation events and notifies connected clients.
type InvitationNotifier struct {
	hub    *Hub
	logger *slog.Logger
}

// NewInvitationNotifier creates a new InvitationNotifier.
func NewInvitationNotifier(hub *Hub, logger *slog.Logger) *InvitationNotifier {
	return &InvitationNotifier{
		hub:    hub,
		logger: logger,
	}
}

type invitationUpdateMsg struct {
	Type string `json:"type"`
}

// OnEvent is called by the Kafka consumer for each stored event.
// If the event is invitation-related, it sends a notification to the target user.
func (n *InvitationNotifier) OnEvent(event *domain.Event) {
	if _, ok := invitationTopics[event.Type]; !ok {
		return
	}
	if event.TargetUserID == nil || *event.TargetUserID == "" {
		return
	}

	msg, err := json.Marshal(invitationUpdateMsg{Type: "invitation_update"})
	if err != nil {
		n.logger.Error("failed to marshal ws message", "error", err)
		return
	}

	n.hub.NotifyUser(*event.TargetUserID, msg)
}
