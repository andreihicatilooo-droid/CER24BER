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
		`INSERT INTO transactions (id, service_id, user_hash, type, amount_usdt, amount_rub, rate, description, created_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
		t.ID, t.ServiceID, t.UserHash, t.Type, t.AmountUSDT, t.AmountRUB, t.Rate, t.Description, t.CreatedAt,
	)
	return err
}

func (r *TransactionRepo) ListByUser(ctx context.Context, serviceID, userHash string, limit, offset int) ([]model.Transaction, error) {
	var txs []model.Transaction
	err := r.db.SelectContext(ctx, &txs,
		`SELECT id, service_id, user_hash, type, amount_usdt, amount_rub, rate, description, created_at
		 FROM transactions
		 WHERE service_id = $1 AND user_hash = $2
		 ORDER BY created_at DESC LIMIT $3 OFFSET $4`,
		serviceID, userHash, limit, offset,
	)
	return txs, err
}

// ListByAccount returns paginated transactions for a given account (as sender or receiver).
func (r *TransactionRepo) ListByAccount(ctx context.Context, accountID string, limit, offset int) ([]model.Transaction, error) {
	var txs []model.Transaction
	err := r.db.SelectContext(ctx, &txs,
		`SELECT id, from_account_id, to_account_id, amount, type, description, created_at
		 FROM transactions
		 WHERE from_account_id = $1 OR to_account_id = $1
		 ORDER BY created_at DESC LIMIT $2 OFFSET $3`,
		accountID, limit, offset,
	)
	return txs, err
}

// ListByService returns all transactions for accounts owned by service's user scope.
func (r *TransactionRepo) ListByService(ctx context.Context, serviceID string, limit, offset int) ([]model.Transaction, error) {
	var txs []model.Transaction
	err := r.db.SelectContext(ctx, &txs,
		`SELECT t.id, t.from_account_id, t.to_account_id, t.amount, t.type, t.description, t.created_at
		 FROM transactions t
		 JOIN accounts a ON a.id = t.from_account_id OR a.id = t.to_account_id
		 JOIN service_accounts sa ON sa.account_id = a.id
		 WHERE sa.service_id = $1
		 ORDER BY t.created_at DESC LIMIT $2 OFFSET $3`,
		serviceID, limit, offset,
	)
	return txs, err
}
