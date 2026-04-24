FROM golang:1.23-alpine AS builder

WORKDIR /app

# Copy pkg module (needed by replace directive)
COPY backend/pkg/ ./backend/pkg/

# Copy proto contracts module (needed by replace directive)
COPY contracts/proto/ ./contracts/proto/

# Copy service module
COPY backend/services/billing-service/ ./backend/services/billing-service/

WORKDIR /app/backend/services/billing-service
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /service ./cmd

FROM gcr.io/distroless/static:nonroot

COPY --from=builder /service /service

ENTRYPOINT ["/service"]
