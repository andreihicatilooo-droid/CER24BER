package config

import (
	"encoding/hex"
	"errors"
	"os"
)

// Config holds all runtime configuration for CERBER CORE.
type Config struct {
	BillingDSN    string
	ServerPort    string
	AdminKey      string // protects POST /admin/services
	MasterAESKey  []byte // 32 bytes — encrypts service secret keys stored in DB
	MasterHMACKey []byte // 32 bytes — hashes API keys stored in DB
}

// Load reads configuration from environment variables.
// MASTER_AES_KEY and MASTER_HMAC_KEY must be 64-char hex strings (32 bytes each).
func Load() (*Config, error) {
	aesKey, err := hexKey("MASTER_AES_KEY")
	if err != nil {
		return nil, err
	}
	hmacKey, err := hexKey("MASTER_HMAC_KEY")
	if err != nil {
		return nil, err
	}
	adminKey := os.Getenv("ADMIN_KEY")
	if adminKey == "" {
		return nil, errors.New("ADMIN_KEY env var is required")
	}
	return &Config{
		BillingDSN:    getEnv("BILLING_DSN", "postgres://billing:billing@localhost:5432/billing?sslmode=disable"),
		ServerPort:    getEnv("SERVER_PORT", "8080"),
		AdminKey:      adminKey,
		MasterAESKey:  aesKey,
		MasterHMACKey: hmacKey,
	}, nil
}

func hexKey(envName string) ([]byte, error) {
	val := os.Getenv(envName)
	if val == "" {
		return nil, errors.New(envName + " env var is required")
	}
	key, err := hex.DecodeString(val)
	if err != nil || len(key) != 32 {
		return nil, errors.New(envName + " must be exactly 64 hex characters (32 bytes)")
	}
	return key, nil
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
