package repository

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"github.com/cerber/billing/internal/model"
	"github.com/google/uuid"
	"github.com/jmoiron/sqlx"
)

type BalanceRepo struct {
	db *sqlx.DB
}

func NewBalanceRepo(db *sqlx.DB) *BalanceRepo {
	return &BalanceRepo{db: db}
}

func (r *BalanceRepo) FindOrCreate(ctx context.Context, serviceID, userHash string) (*model.ServiceBalance, error) {
	var b model.ServiceBalance
	err := r.db.GetContext(ctx, &b,
		`SELECT id, service_id, user_hash, balance_usdt, updated_at
		 FROM service_balances WHERE service_id = $1 AND user_hash = $2`,
		serviceID, userHash)
	if errors.Is(err, sql.ErrNoRows) {
		b = model.ServiceBalance{
			ID:          uuid.NewString(),
			ServiceID:   serviceID,
			UserHash:    userHash,
			BalanceUSDT: 0,
			UpdatedAt:   time.Now(),
		}
		_, err = r.db.ExecContext(ctx,
			`INSERT INTO service_balances (id, service_id, user_hash, balance_usdt, updated_at)
			 VALUES ($1, $2, $3, $4, $5)`,
			b.ID, b.ServiceID, b.UserHash, b.BalanceUSDT, b.UpdatedAt,
		)
		if err != nil {
			return nil, err
		}
		return &b, nil
	}
	return &b, err
}

// AddUSDT atomically adds delta (positive = credit, negative = debit) to balance.
func (r *BalanceRepo) AddUSDT(ctx context.Context, serviceID, userHash string, delta float64) error {
	result, err := r.db.ExecContext(ctx,
		`UPDATE service_balances
		 SET balance_usdt = balance_usdt + $1, updated_at = NOW()
		 WHERE service_id = $2 AND user_hash = $3 AND balance_usdt + $1 >= 0`,
		delta, serviceID, userHash)
	if err != nil {
		return err
	}
	n, err := result.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return errors.New("insufficient funds or account not found")
	}
	return nil
}
