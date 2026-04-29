FROM golang:1.22-alpine AS builder
WORKDIR /app

# Download deps first (cached layer)
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /cerbercore ./cmd/api

# ─── Minimal runtime image ────────────────────────────────────────────────────
FROM alpine:3.19
RUN apk --no-cache add ca-certificates tzdata

WORKDIR /app
COPY --from=builder /cerbercore .

EXPOSE 8080
ENTRYPOINT ["/app/cerbercore"]

