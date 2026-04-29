package repository

import (
	"context"
	"database/sql"
	"errors"
	"time"

	"github.com/cerber/billing/internal/model"
	"github.com/jmoiron/sqlx"
)

type UserRepo struct {
	db *sqlx.DB
}

func NewUserRepo(db *sqlx.DB) *UserRepo {
	return &UserRepo{db: db}
}

// Upsert inserts a billing user if not present, otherwise returns existing record.
func (r *UserRepo) Upsert(ctx context.Context, userHash string) (*model.BillingUser, error) {
	_, err := r.db.ExecContext(ctx,
		`INSERT INTO users (user_hash, status, created_at)
		 VALUES ($1, 'active', $2)
		 ON CONFLICT (user_hash) DO NOTHING`,
		userHash, time.Now(),
	)
	if err != nil {
		return nil, err
	}
	return r.FindByHash(ctx, userHash)
}

func (r *UserRepo) FindByHash(ctx context.Context, userHash string) (*model.BillingUser, error) {
	var u model.BillingUser
	err := r.db.GetContext(ctx, &u,
		`SELECT user_hash, status, created_at FROM users WHERE user_hash = $1`, userHash)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, errors.New("user not found")
	}
	return &u, err
}
