FROM golang:1.23-alpine AS builder

WORKDIR /app

# Copy pkg module (needed by replace directive)
COPY backend/pkg/ ./backend/pkg/

# Copy service module
COPY backend/services/identity-service/ ./backend/services/identity-service/

WORKDIR /app/backend/services/identity-service
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /service ./cmd

FROM gcr.io/distroless/static:nonroot

COPY --from=builder /service /service

ENTRYPOINT ["/service"]
