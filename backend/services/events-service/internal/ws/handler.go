package ws

import (
	"log/slog"
	"net/http"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"

	"github.com/gaev-tech/api-tracker/events-service/internal/middleware"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		return true // nginx handles CORS
	},
}

// HandleWebSocket returns a Gin handler that upgrades to a WebSocket connection.
// Authentication is handled by nginx auth_request; the user ID is read from X-User-Id.
func HandleWebSocket(hub *Hub, logger *slog.Logger) gin.HandlerFunc {
	return func(c *gin.Context) {
		userID, _ := c.Get(middleware.UserIDKey)
		uid, ok := userID.(string)
		if !ok || uid == "" {
			c.JSON(http.StatusUnauthorized, gin.H{
				"error": gin.H{"code": "unauthorized", "message": "missing user id"},
			})
			return
		}

		conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
		if err != nil {
			logger.Error("ws upgrade failed", "error", err, "user_id", uid)
			return
		}

		client := &Client{
			userID: uid,
			conn:   conn,
			send:   make(chan []byte, 64),
			hub:    hub,
		}

		hub.Register(client)

		go client.writePump()
		go client.readPump()
	}
}
