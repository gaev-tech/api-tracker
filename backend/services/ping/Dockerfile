FROM golang:1.23-alpine AS builder

WORKDIR /app

# Copy pkg module (needed by replace directive)
COPY backend/pkg/ ./backend/pkg/

# Copy service module
COPY backend/services/ping/ ./backend/services/ping/

WORKDIR /app/backend/services/ping
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux go build -o /ping ./cmd/main.go

FROM alpine:3.20

RUN addgroup -S app && adduser -S app -G app
USER app

COPY --from=builder /ping /ping
COPY --from=builder /app/backend/services/ping/migrations /migrations

EXPOSE 8080

CMD ["/ping"]
