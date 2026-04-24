package store

import (
	"errors"

	"github.com/lib/pq"
)

var ErrNotFound = errors.New("store: not found")
var ErrConflict = errors.New("store: conflict")

func isPgUniqueViolation(err error) bool {
	var pqErr *pq.Error
	return errors.As(err, &pqErr) && pqErr.Code == "23505"
}
