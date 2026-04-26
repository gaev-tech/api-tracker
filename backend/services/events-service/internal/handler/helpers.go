package handler

import (
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
)

func apiErr(code, message string, details interface{}) gin.H {
	e := gin.H{"code": code, "message": message}
	if details != nil {
		e["details"] = details
	}
	return gin.H{"error": e}
}

func parseLimit(c *gin.Context, defaultVal, maxVal int) int {
	limit := defaultVal
	if l := c.Query("limit"); l != "" {
		parsed, err := strconv.Atoi(l)
		if err == nil && parsed > 0 {
			limit = parsed
		}
	}
	if limit > maxVal {
		limit = maxVal
	}
	return limit
}

func parseSort(c *gin.Context, defaultField, defaultDir string) (field, dir string) {
	s := c.Query("sort")
	if s == "" {
		return defaultField, defaultDir
	}
	parts := strings.SplitN(s, ":", 2)
	field = parts[0]
	dir = defaultDir
	if len(parts) == 2 {
		dir = parts[1]
	}
	return field, dir
}
