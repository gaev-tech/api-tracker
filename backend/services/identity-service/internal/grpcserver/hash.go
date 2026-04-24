package grpcserver

import (
	"crypto/sha256"
	"fmt"
)

func hashToken(token string) string {
	sum := sha256.Sum256([]byte(token))
	return fmt.Sprintf("%x", sum)
}
