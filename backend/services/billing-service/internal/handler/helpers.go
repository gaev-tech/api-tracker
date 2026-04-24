package handler

import "github.com/gin-gonic/gin"

func APIErr(code, message string, details interface{}) gin.H {
	e := gin.H{"code": code, "message": message}
	if details != nil {
		e["details"] = details
	}
	return gin.H{"error": e}
}
