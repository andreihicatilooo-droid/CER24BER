package repository

import (
	"context"
	"database/sql"
	"errors"

	"github.com/cerber/billing/internal/model"
	"github.com/jmoiron/sqlx"
)

type TopupRepo struct {
	db *sqlx.DB
}

func NewTopupRepo(db *sqlx.DB) *TopupRepo {
	return &TopupRepo{db: db}
}

func (r *TopupRepo) ListMethods(ctx context.Context) ([]model.TopupMethod, error) {
	var methods []model.TopupMethod
	err := r.db.SelectContext(ctx, &methods,
		`SELECT id, name, code, fee_percent, min_amount, max_amount, currency, is_active
		 FROM topup_methods WHERE is_active = true ORDER BY name`)
	return methods, err
}

func (r *TopupRepo) CreateSession(ctx context.Context, s *model.TopupSession) error {
	_, err := r.db.ExecContext(ctx,
		`INSERT INTO topup_sessions
		 (id, service_id, user_hash, method_id, amount_usdt, amount_rub, rate, status, payment_url, requisites, created_at, updated_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)`,
		s.ID, s.ServiceID, s.UserHash, s.MethodID,
		s.AmountUSDT, s.AmountRUB, s.Rate,
		s.Status, s.PaymentURL, s.Requisites,
		s.CreatedAt, s.UpdatedAt,
	)
	return err
}

func (r *TopupRepo) FindSessionByID(ctx context.Context, id string) (*model.TopupSession, error) {
	var s model.TopupSession
	err := r.db.GetContext(ctx, &s,
		`SELECT id, service_id, user_hash, method_id, amount_usdt, amount_rub, rate,
		        status, payment_url, requisites, created_at, updated_at
		 FROM topup_sessions WHERE id = $1`, id)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, errors.New("topup session not found")
	}
	return &s, err
}

func (r *TopupRepo) UpdateSessionStatus(ctx context.Context, id string, status model.TopupStatus) error {
	_, err := r.db.ExecContext(ctx,
		`UPDATE topup_sessions SET status = $1, updated_at = NOW() WHERE id = $2`,
		status, id)
	return err
}
