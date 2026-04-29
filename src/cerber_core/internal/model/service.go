package model

import "time"

// Service represents a tenant service that consumes the billing API.
// api_key_hash  — HMAC-SHA256(raw_api_key, master_hmac_key), stored for lookup.
// secret_key_encrypted — AES-GCM-256(32-byte secret, master_aes_key), stored encrypted.
type Service struct {
	ID                 string    `db:"id"                   json:"id"`
	Name               string    `db:"name"                 json:"name"`
	APIKeyHash         string    `db:"api_key_hash"         json:"-"`
	SecretKeyEncrypted string    `db:"secret_key_encrypted" json:"-"`
	IsActive           bool      `db:"is_active"            json:"is_active"`
	CreatedAt          time.Time `db:"created_at"           json:"created_at"`

	// Transient — populated after decryption, never persisted.
	SecretKey []byte `db:"-" json:"-"`
}
