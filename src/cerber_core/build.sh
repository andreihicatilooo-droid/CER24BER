#!/usr/bin/env sh
# build.sh — one-shot dev setup
set -e

echo "==> Installing swag CLI..."
go install github.com/swaggo/swag/cmd/swag@latest

echo "==> Generating Swagger docs..."
swag init -g cmd/api/main.go -o docs

echo "==> Downloading dependencies..."
go mod tidy

echo "==> Building binary..."
go build -o billing ./cmd/api

echo "Done. Run: ./billing"
