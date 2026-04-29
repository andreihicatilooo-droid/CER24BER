package model

import "time"

// ExchangeRate stores the USDT→RUB (or any pair) conversion rate.
type ExchangeRate struct {
	ID        int       `db:"id"         json:"id"`
	Source    string    `db:"source"     json:"source"`
	Target    string    `db:"target"     json:"target"`
	Rate      float64   `db:"rate"       json:"rate"`
	UpdatedAt time.Time `db:"updated_at" json:"updated_at"`
}
