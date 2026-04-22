package metrics

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

var (
	requestsTotal = prometheus.NewCounterVec(
		prometheus.CounterOpts{
			Name: "http_requests_total",
			Help: "Total number of HTTP requests.",
		},
		[]string{"service", "method", "path", "status"},
	)

	requestDuration = prometheus.NewHistogramVec(
		prometheus.HistogramOpts{
			Name:    "http_request_duration_seconds",
			Help:    "HTTP request duration in seconds.",
			Buckets: prometheus.DefBuckets,
		},
		[]string{"service", "method", "path"},
	)
)

func init() {
	prometheus.MustRegister(requestsTotal, requestDuration)
}

// Middleware returns a Gin middleware that records request count and duration.
func Middleware(service string) gin.HandlerFunc {
	return func(c *gin.Context) {
		timer := prometheus.NewTimer(requestDuration.WithLabelValues(
			service, c.Request.Method, c.FullPath(),
		))

		c.Next()

		timer.ObserveDuration()
		requestsTotal.WithLabelValues(
			service,
			c.Request.Method,
			c.FullPath(),
			strconv.Itoa(c.Writer.Status()),
		).Inc()
	}
}

// Handler returns an HTTP handler that serves Prometheus metrics.
func Handler() http.Handler {
	return promhttp.Handler()
}
