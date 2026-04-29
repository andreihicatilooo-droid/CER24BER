package model

import "time"

type TopupStatus string

const (
	TopupPending   TopupStatus = "pending"
	TopupConfirmed TopupStatus = "confirmed"
	TopupFailed    TopupStatus = "failed"
	TopupExpired   TopupStatus = "expired"
)

// TopupSession tracks a single payer top-up attempt from initiation to confirmation.
type TopupSession struct {
	ID         string      `db:"id"          json:"id"`
	ServiceID  string      `db:"service_id"  json:"service_id"`
	UserHash   string      `db:"user_hash"   json:"user_hash"`
	MethodID   string      `db:"method_id"   json:"method_id"`
	AmountUSDT float64     `db:"amount_usdt" json:"amount_usdt"`
	AmountRUB  float64     `db:"amount_rub"  json:"amount_rub"`
	Rate       float64     `db:"rate"        json:"rate"`
	Status     TopupStatus `db:"status"      json:"status"`
	PaymentURL string      `db:"payment_url" json:"payment_url"`
	Requisites string      `db:"requisites"  json:"requisites"` // JSON blob
	CreatedAt  time.Time   `db:"created_at"  json:"created_at"`
	UpdatedAt  time.Time   `db:"updated_at"  json:"updated_at"`
}

// TopupMethod describes an available deposit gateway with fees.
type TopupMethod struct {
	ID         string  `db:"id"          json:"id"`
	Name       string  `db:"name"        json:"name"`
	Code       string  `db:"code"        json:"code"`
	FeePercent float64 `db:"fee_percent" json:"fee_percent"`
	MinAmount  float64 `db:"min_amount"  json:"min_amount"`
	MaxAmount  float64 `db:"max_amount"  json:"max_amount"`
	Currency   string  `db:"currency"    json:"currency"`
	IsActive   bool    `db:"is_active"   json:"is_active"`
}
