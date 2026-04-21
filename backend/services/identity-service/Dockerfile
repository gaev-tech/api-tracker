FROM golang:1.23-alpine AS builder

WORKDIR /app

COPY go.mod ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /service ./cmd

FROM gcr.io/distroless/static:nonroot

COPY --from=builder /service /service

ENTRYPOINT ["/service"]
