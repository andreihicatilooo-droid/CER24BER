package repository

import (
	"context"
	"database/sql"
	"errors"

	"github.com/cerber/billing/internal/model"
	"github.com/jmoiron/sqlx"
)

type ServiceRepo struct {
	db *sqlx.DB
}

func NewServiceRepo(db *sqlx.DB) *ServiceRepo {
	return &ServiceRepo{db: db}
}

func (r *ServiceRepo) Create(ctx context.Context, s *model.Service) error {
	_, err := r.db.ExecContext(ctx,
		`INSERT INTO services (id, name, api_key_hash, secret_key_encrypted, is_active, created_at)
		 VALUES ($1, $2, $3, $4, $5, $6)`,
		s.ID, s.Name, s.APIKeyHash, s.SecretKeyEncrypted, s.IsActive, s.CreatedAt,
	)
	return err
}

// FindByAPIKeyHash looks up a service by the HMAC-SHA256 hash of its raw API key.
func (r *ServiceRepo) FindByAPIKeyHash(ctx context.Context, hash string) (*model.Service, error) {
	var s model.Service
	err := r.db.GetContext(ctx, &s,
		`SELECT id, name, api_key_hash, secret_key_encrypted, is_active, created_at
		 FROM services WHERE api_key_hash = $1 AND is_active = true`, hash)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, errors.New("service not found or inactive")
	}
	return &s, err
}

func (r *ServiceRepo) List(ctx context.Context) ([]model.Service, error) {
	var services []model.Service
	err := r.db.SelectContext(ctx, &services,
		`SELECT id, name, api_key_hash, is_active, created_at FROM services ORDER BY created_at`)
	return services, err
}
