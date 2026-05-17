package model

import "time"

type TxType string

const (
	TxTopup    TxType = "topup"
	TxTransfer TxType = "transfer"
	TxWithdraw TxType = "withdrawal"
)

// Transaction is the immutable audit log of every balance change.
// Base currency is USDT; amount_rub is the RUB equivalent at the time of the operation.
type Transaction struct {
	ID          string    `db:"id"          json:"id"`
	ServiceID   string    `db:"service_id"  json:"service_id"`
	UserHash    string    `db:"user_hash"   json:"user_hash"`
	OperationID string    `db:"operation_id" json:"operation_id"`
	Type        TxType    `db:"type"        json:"type"`
	AmountUSDT  float64   `db:"amount_usdt" json:"amount_usdt"`
	AmountRUB   float64   `db:"amount_rub"  json:"amount_rub"`
	Rate        float64   `db:"rate"        json:"rate"`
	Description string    `db:"description" json:"description"`
	CreatedAt   time.Time `db:"created_at"  json:"created_at"`
}
