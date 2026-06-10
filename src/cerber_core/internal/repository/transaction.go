package repository

import (
	"context"

	"github.com/cerber/billing/internal/model"
	"github.com/jmoiron/sqlx"
)

type TransactionRepo struct {
	db *sqlx.DB
}

func NewTransactionRepo(db *sqlx.DB) *TransactionRepo {
	return &TransactionRepo{db: db}
}

func (r *TransactionRepo) Create(ctx context.Context, t *model.Transaction) error {
	_, err := r.db.ExecContext(ctx,
		`INSERT INTO transactions (id, service_id, user_hash, operation_id, type, amount_usdt, amount_rub, rate, description, created_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
		t.ID, t.ServiceID, t.UserHash, t.OperationID, t.Type, t.AmountUSDT, t.AmountRUB, t.Rate, t.Description, t.CreatedAt,
	)
	return err
}

func (r *TransactionRepo) ListByUser(ctx context.Context, serviceID, userHash string, limit, offset int) ([]model.Transaction, error) {
	var txs []model.Transaction
	err := r.db.SelectContext(ctx, &txs,
		`SELECT id, service_id, user_hash, operation_id, type, amount_usdt, amount_rub, rate, description, created_at
		 FROM transactions
		 WHERE service_id = $1 AND user_hash = $2
		 ORDER BY created_at DESC LIMIT $3 OFFSET $4`,
		serviceID, userHash, limit, offset,
	)
	return txs, err
}

// ListByService returns paginated transactions for all users within a service scope.
func (r *TransactionRepo) ListByService(ctx context.Context, serviceID string, limit, offset int) ([]model.Transaction, error) {
	var txs []model.Transaction
	err := r.db.SelectContext(ctx, &txs,
		`SELECT id, service_id, user_hash, operation_id, type, amount_usdt, amount_rub, rate, description, created_at
		 FROM transactions
		 WHERE service_id = $1
		 ORDER BY created_at DESC LIMIT $2 OFFSET $3`,
		serviceID, limit, offset,
	)
	return txs, err
}
