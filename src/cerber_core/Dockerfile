FROM golang:1.22-alpine AS builder
WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN go install github.com/swaggo/swag/cmd/swag@latest && \
    swag init -g cmd/api/main.go -o docs && \
    CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /billing ./cmd/api

# ─── Runtime image ────────────────────────────────────────────────────────────
FROM alpine:3.19
RUN apk --no-cache add ca-certificates tzdata

WORKDIR /app
COPY --from=builder /billing .
COPY migrations/ ./migrations/

EXPOSE 8080
ENTRYPOINT ["/app/billing"]
