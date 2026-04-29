package model

import "time"

// BillingUser is the billing registry entry for a user.
// No PII is stored here — only the opaque user_hash (SHA-256 of the real user ID
// computed client-side before the hash is encrypted and sent to the API).
type BillingUser struct {
	UserHash  string    `db:"user_hash"  json:"user_hash"`
	Status    string    `db:"status"     json:"status"`
	CreatedAt time.Time `db:"created_at" json:"created_at"`
}
