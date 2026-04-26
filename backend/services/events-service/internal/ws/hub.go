package ws

import (
	"log/slog"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

const (
	writeWait  = 10 * time.Second
	pongWait   = 60 * time.Second
	pingPeriod = (pongWait * 9) / 10
)

// Hub manages WebSocket connections grouped by user ID.
type Hub struct {
	clients map[string]map[*Client]struct{}
	mu      sync.RWMutex
	logger  *slog.Logger
}

// Client represents a single WebSocket connection.
type Client struct {
	userID string
	conn   *websocket.Conn
	send   chan []byte
	hub    *Hub
}

// NewHub creates a new Hub.
func NewHub(logger *slog.Logger) *Hub {
	return &Hub{
		clients: make(map[string]map[*Client]struct{}),
		logger:  logger,
	}
}

// Register adds a client to the hub.
func (h *Hub) Register(client *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.clients[client.userID] == nil {
		h.clients[client.userID] = make(map[*Client]struct{})
	}
	h.clients[client.userID][client] = struct{}{}
	h.logger.Info("ws client registered", "user_id", client.userID)
}

// Unregister removes a client from the hub and closes its connection.
func (h *Hub) Unregister(client *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if conns, ok := h.clients[client.userID]; ok {
		if _, exists := conns[client]; exists {
			delete(conns, client)
			close(client.send)
			if len(conns) == 0 {
				delete(h.clients, client.userID)
			}
		}
	}
	client.conn.Close()
	h.logger.Info("ws client unregistered", "user_id", client.userID)
}

// NotifyUser sends data to all connections of the given user.
func (h *Hub) NotifyUser(userID string, data []byte) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	conns, ok := h.clients[userID]
	if !ok {
		return
	}
	for c := range conns {
		select {
		case c.send <- data:
		default:
			// drop message if client is slow
			h.logger.Warn("ws send buffer full, dropping message", "user_id", userID)
		}
	}
}

// writePump pumps messages from the send channel to the WebSocket connection.
func (c *Client) writePump() {
	ticker := time.NewTicker(pingPeriod)
	defer func() {
		ticker.Stop()
		c.hub.Unregister(c)
	}()
	for {
		select {
		case msg, ok := <-c.send:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if !ok {
				c.conn.WriteMessage(websocket.CloseMessage, nil)
				return
			}
			if err := c.conn.WriteMessage(websocket.TextMessage, msg); err != nil {
				return
			}
		case <-ticker.C:
			c.conn.SetWriteDeadline(time.Now().Add(writeWait))
			if err := c.conn.WriteMessage(websocket.PingMessage, nil); err != nil {
				return
			}
		}
	}
}

// readPump reads messages from the WebSocket connection to detect disconnection.
func (c *Client) readPump() {
	defer c.hub.Unregister(c)
	c.conn.SetReadLimit(512)
	c.conn.SetReadDeadline(time.Now().Add(pongWait))
	c.conn.SetPongHandler(func(string) error {
		c.conn.SetReadDeadline(time.Now().Add(pongWait))
		return nil
	})
	for {
		if _, _, err := c.conn.ReadMessage(); err != nil {
			break
		}
	}
}
