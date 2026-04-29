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

func (r *AccountRepo) Create(ctx context.Context, a *model.Account) error {
	_, err := r.db.ExecContext(ctx,
		`INSERT INTO accounts (id, user_id, name, currency, balance, created_at, updated_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7)`,
		a.ID, a.UserID, a.Name, a.Currency, a.Balance, a.CreatedAt, a.UpdatedAt,
	)
	return err
}

func (r *AccountRepo) FindByID(ctx context.Context, id string) (*model.Account, error) {
	var a model.Account
	err := r.db.GetContext(ctx, &a,
		`SELECT id, user_id, name, currency, balance, created_at, updated_at FROM accounts WHERE id = $1`, id)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, errors.New("account not found")
	}
	return &a, err
}

func (r *AccountRepo) FindByUserID(ctx context.Context, userID string) ([]model.Account, error) {
	var accounts []model.Account
	err := r.db.SelectContext(ctx, &accounts,
		`SELECT id, user_id, name, currency, balance, created_at, updated_at
		 FROM accounts WHERE user_id = $1 ORDER BY created_at`, userID)
	return accounts, err
}

// FindByProvider returns all acquiring accounts linked to a provider.
func (r *AccountRepo) FindByProvider(ctx context.Context, providerID string) ([]model.Account, error) {
	var accounts []model.Account
	err := r.db.SelectContext(ctx, &accounts,
		`SELECT a.id, a.user_id, a.name, a.currency, a.balance, a.created_at, a.updated_at
		 FROM accounts a
		 JOIN account_providers ap ON ap.account_id = a.id
		 WHERE ap.provider_id = $1 ORDER BY a.created_at`, providerID)
	return accounts, err
}

// UpdateBalance atomically changes balance by delta (positive or negative).
func (r *AccountRepo) UpdateBalance(ctx context.Context, tx *sql.Tx, id string, delta float64) error {
	result, err := tx.ExecContext(ctx,
		`UPDATE accounts SET balance = balance + $1, updated_at = NOW() WHERE id = $2 AND balance + $1 >= 0`,
		delta, id,
	)
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

// TotalBalance returns the sum of all balances in a given currency.
func (r *AccountRepo) TotalBalance(ctx context.Context, currency string) (float64, error) {
	var total float64
	err := r.db.GetContext(ctx, &total,
		`SELECT COALESCE(SUM(balance), 0) FROM accounts WHERE currency = $1`, currency)
	return total, err
}
