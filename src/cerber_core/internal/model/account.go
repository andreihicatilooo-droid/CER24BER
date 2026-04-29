package model

import "time"

// ServiceBalance holds the USDT balance of a user within a specific service scope.
type ServiceBalance struct {
	ID          string    `db:"id"           json:"id"`
	ServiceID   string    `db:"service_id"   json:"service_id"`
	UserHash    string    `db:"user_hash"    json:"user_hash"`
	BalanceUSDT float64   `db:"balance_usdt" json:"balance_usdt"`
	UpdatedAt   time.Time `db:"updated_at"   json:"updated_at"`
}
