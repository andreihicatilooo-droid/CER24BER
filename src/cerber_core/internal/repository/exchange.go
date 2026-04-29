package repository

import (
	"context"
	"database/sql"
	"errors"

	"github.com/cerber/billing/internal/model"
	"github.com/jmoiron/sqlx"
)

type ExchangeRepo struct {
	db *sqlx.DB
}

func NewExchangeRepo(db *sqlx.DB) *ExchangeRepo {
	return &ExchangeRepo{db: db}
}

// GetRate returns the latest exchange rate for a currency pair.
func (r *ExchangeRepo) GetRate(ctx context.Context, source, target string) (*model.ExchangeRate, error) {
	var rate model.ExchangeRate
	err := r.db.GetContext(ctx, &rate,
		`SELECT id, source, target, rate, updated_at
		 FROM exchange_rates
		 WHERE source = $1 AND target = $2
		 ORDER BY updated_at DESC LIMIT 1`,
		source, target)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, errors.New("exchange rate not found for " + source + "/" + target)
	}
	return &rate, err
}

// Upsert inserts or updates the exchange rate for a pair.
func (r *ExchangeRepo) Upsert(ctx context.Context, source, target string, rate float64) error {
	_, err := r.db.ExecContext(ctx,
		`INSERT INTO exchange_rates (source, target, rate, updated_at)
		 VALUES ($1, $2, $3, NOW())
		 ON CONFLICT (source, target) DO UPDATE SET rate = $3, updated_at = NOW()`,
		source, target, rate)
	return err
}
