package service

import (
	"context"
	"database/sql"
	"errors"
	"math"
	"time"

	"github.com/cerber/billing/internal/model"
	"github.com/cerber/billing/internal/repository"
	"github.com/google/uuid"
	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
)

type BalanceService struct {
	db           *sqlx.DB
	userRepo     *repository.UserRepo
	balanceRepo  *repository.BalanceRepo
	txRepo       *repository.TransactionRepo
	exchangeRepo *repository.ExchangeRepo
}

var ErrInsufficientFunds = errors.New("insufficient funds")

func NewBalanceService(
	db *sqlx.DB,
	userRepo *repository.UserRepo,
	balanceRepo *repository.BalanceRepo,
	txRepo *repository.TransactionRepo,
	exchangeRepo *repository.ExchangeRepo,
) *BalanceService {
	return &BalanceService{
		db:           db,
		userRepo:     userRepo,
		balanceRepo:  balanceRepo,
		txRepo:       txRepo,
		exchangeRepo: exchangeRepo,
	}
}

type BalanceResult struct {
	BalanceUSDT float64 `json:"balance_usdt"`
	BalanceRUB  float64 `json:"balance_rub"`
	Rate        float64 `json:"rate_usdt_rub"`
}

// GetBalance returns the user's USDT balance and RUB equivalent.
func (s *BalanceService) GetBalance(ctx context.Context, serviceID, userHash string) (*BalanceResult, error) {
	if err := s.ensureBillingUser(ctx, userHash); err != nil {
		return nil, err
	}
	bal, err := s.balanceRepo.FindOrCreate(ctx, serviceID, userHash)
	if err != nil {
		return nil, err
	}
	rate, err := s.exchangeRepo.GetRate(ctx, "USDT", "RUB")
	if err != nil {
		return nil, err
	}
	return &BalanceResult{
		BalanceUSDT: bal.BalanceUSDT,
		Rate:        rate.Rate,
		BalanceRUB:  bal.BalanceUSDT * rate.Rate,
	}, nil
}

func (s *BalanceService) Adjust(
	ctx context.Context,
	serviceID string,
	userHash string,
	deltaUSDT float64,
	txType model.TxType,
	description string,
	operationID string,
) (*BalanceResult, error) {
	if deltaUSDT == 0 {
		return nil, errors.New("delta_usdt must not be zero")
	}
	if operationID == "" {
		return nil, errors.New("operation_id is required")
	}
	if !isSupportedTxType(txType) {
		return nil, errors.New("unsupported tx_type")
	}
	if err := s.ensureBillingUser(ctx, userHash); err != nil {
		return nil, err
	}

	rate, err := s.exchangeRepo.GetRate(ctx, "USDT", "RUB")
	if err != nil {
		return nil, err
	}

	opts := &sql.TxOptions{Isolation: sql.LevelSerializable}
	tx, err := s.db.BeginTxx(ctx, opts)
	if err != nil {
		return nil, err
	}

	_, err = tx.ExecContext(ctx,
		`INSERT INTO service_balances (id, service_id, user_hash, balance_usdt, updated_at)
		 VALUES ($1, $2, $3, $4, $5)
		 ON CONFLICT (service_id, user_hash) DO NOTHING`,
		uuid.NewString(), serviceID, userHash, 0.0, time.Now(),
	)
	if err != nil {
		_ = tx.Rollback()
		return nil, err
	}

	var currentBalance float64
	err = tx.QueryRowContext(ctx,
		`SELECT balance_usdt FROM service_balances WHERE service_id = $1 AND user_hash = $2 FOR UPDATE`,
		serviceID, userHash,
	).Scan(&currentBalance)
	if err != nil {
		_ = tx.Rollback()
		return nil, err
	}

	if currentBalance+deltaUSDT < 0 {
		_ = tx.Rollback()
		return nil, ErrInsufficientFunds
	}

	_, err = tx.ExecContext(ctx,
		`UPDATE service_balances
		 SET balance_usdt = balance_usdt + $1, updated_at = NOW()
		 WHERE service_id = $2 AND user_hash = $3`,
		deltaUSDT, serviceID, userHash,
	)
	if err != nil {
		_ = tx.Rollback()
		return nil, err
	}

	amountUSDT := math.Abs(deltaUSDT)
	amountRUB := amountUSDT * rate.Rate
	_, err = tx.ExecContext(ctx,
		`INSERT INTO transactions (id, service_id, user_hash, operation_id, type, amount_usdt, amount_rub, rate, description, created_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
		uuid.NewString(), serviceID, userHash, operationID, txType, amountUSDT, amountRUB, rate.Rate, description, time.Now(),
	)
	if err != nil {
		_ = tx.Rollback()
		if isDuplicateOperationError(err) {
			return s.GetBalance(ctx, serviceID, userHash)
		}
		return nil, err
	}

	if err := tx.Commit(); err != nil {
		return nil, err
	}
	return s.GetBalance(ctx, serviceID, userHash)
}

func (s *BalanceService) Hold(
	ctx context.Context,
	serviceID string,
	userHash string,
	amountUSDT float64,
	description string,
	operationID string,
) (*BalanceResult, error) {
	if amountUSDT <= 0 {
		return nil, errors.New("amount_usdt must be > 0")
	}
	return s.Adjust(ctx, serviceID, userHash, -amountUSDT, model.TxTransfer, description, operationID)
}

func (s *BalanceService) Unblock(
	ctx context.Context,
	serviceID string,
	userHash string,
	amountUSDT float64,
	description string,
	operationID string,
) (*BalanceResult, error) {
	if amountUSDT <= 0 {
		return nil, errors.New("amount_usdt must be > 0")
	}
	return s.Adjust(ctx, serviceID, userHash, amountUSDT, model.TxTransfer, description, operationID)
}

func (s *BalanceService) CreateWithdrawal(
	ctx context.Context,
	serviceID string,
	userHash string,
	amountUSDT float64,
	description string,
	operationID string,
) (*BalanceResult, error) {
	if amountUSDT <= 0 {
		return nil, errors.New("amount_usdt must be > 0")
	}
	return s.Adjust(ctx, serviceID, userHash, -amountUSDT, model.TxWithdraw, description, operationID)
}

func (s *BalanceService) CancelWithdrawal(
	ctx context.Context,
	serviceID string,
	userHash string,
	amountUSDT float64,
	description string,
	operationID string,
) (*BalanceResult, error) {
	if amountUSDT <= 0 {
		return nil, errors.New("amount_usdt must be > 0")
	}
	return s.Adjust(ctx, serviceID, userHash, amountUSDT, model.TxTransfer, description, operationID)
}

func (s *BalanceService) Transfer(
	ctx context.Context,
	serviceID string,
	fromUserHash string,
	toUserHash string,
	amountUSDT float64,
	description string,
	operationID string,
) (*BalanceResult, *BalanceResult, error) {
	if amountUSDT <= 0 {
		return nil, nil, errors.New("amount_usdt must be > 0")
	}
	if operationID == "" {
		return nil, nil, errors.New("operation_id is required")
	}
	if fromUserHash == toUserHash {
		return nil, nil, errors.New("from and to user must differ")
	}
	if err := s.ensureBillingUser(ctx, fromUserHash); err != nil {
		return nil, nil, err
	}
	if err := s.ensureBillingUser(ctx, toUserHash); err != nil {
		return nil, nil, err
	}

	rate, err := s.exchangeRepo.GetRate(ctx, "USDT", "RUB")
	if err != nil {
		return nil, nil, err
	}

	opts := &sql.TxOptions{Isolation: sql.LevelSerializable}
	tx, err := s.db.BeginTxx(ctx, opts)
	if err != nil {
		return nil, nil, err
	}

	_, err = tx.ExecContext(ctx,
		`INSERT INTO service_balances (id, service_id, user_hash, balance_usdt, updated_at)
		 VALUES ($1, $2, $3, $4, $5)
		 ON CONFLICT (service_id, user_hash) DO NOTHING`,
		uuid.NewString(), serviceID, fromUserHash, 0.0, time.Now(),
	)
	if err != nil {
		_ = tx.Rollback()
		return nil, nil, err
	}
	_, err = tx.ExecContext(ctx,
		`INSERT INTO service_balances (id, service_id, user_hash, balance_usdt, updated_at)
		 VALUES ($1, $2, $3, $4, $5)
		 ON CONFLICT (service_id, user_hash) DO NOTHING`,
		uuid.NewString(), serviceID, toUserHash, 0.0, time.Now(),
	)
	if err != nil {
		_ = tx.Rollback()
		return nil, nil, err
	}

	var currentFromBalance, currentToBalance float64
	err = tx.QueryRowContext(ctx,
		`SELECT balance_usdt FROM service_balances WHERE service_id = $1 AND user_hash = $2 FOR UPDATE`,
		serviceID, fromUserHash,
	).Scan(&currentFromBalance)
	if err != nil {
		_ = tx.Rollback()
		return nil, nil, err
	}

	err = tx.QueryRowContext(ctx,
		`SELECT balance_usdt FROM service_balances WHERE service_id = $1 AND user_hash = $2 FOR UPDATE`,
		serviceID, toUserHash,
	).Scan(&currentToBalance)
	if err != nil {
		_ = tx.Rollback()
		return nil, nil, err
	}

	if currentFromBalance-amountUSDT < 0 {
		_ = tx.Rollback()
		return nil, nil, ErrInsufficientFunds
	}

	_, err = tx.ExecContext(ctx,
		`UPDATE service_balances
		 SET balance_usdt = balance_usdt - $1, updated_at = NOW()
		 WHERE service_id = $2 AND user_hash = $3`,
		amountUSDT, serviceID, fromUserHash,
	)
	if err != nil {
		_ = tx.Rollback()
		return nil, nil, err
	}

	_, err = tx.ExecContext(ctx,
		`UPDATE service_balances
		 SET balance_usdt = balance_usdt + $1, updated_at = NOW()
		 WHERE service_id = $2 AND user_hash = $3`,
		amountUSDT, serviceID, toUserHash,
	)
	if err != nil {
		_ = tx.Rollback()
		return nil, nil, err
	}

	amountRUB := amountUSDT * rate.Rate
	_, err = tx.ExecContext(ctx,
		`INSERT INTO transactions (id, service_id, user_hash, operation_id, type, amount_usdt, amount_rub, rate, description, created_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10),
		        ($11, $12, $13, $14, $15, $16, $17, $18, $19, $20)`,
		uuid.NewString(), serviceID, fromUserHash, operationID+":out", model.TxTransfer, amountUSDT, amountRUB, rate.Rate, description, time.Now(),
		uuid.NewString(), serviceID, toUserHash, operationID+":in", model.TxTransfer, amountUSDT, amountRUB, rate.Rate, description, time.Now(),
	)
	if err != nil {
		_ = tx.Rollback()
		if isDuplicateOperationError(err) {
			fromBalance, fromErr := s.GetBalance(ctx, serviceID, fromUserHash)
			toBalance, toErr := s.GetBalance(ctx, serviceID, toUserHash)
			if fromErr != nil {
				return nil, nil, fromErr
			}
			if toErr != nil {
				return nil, nil, toErr
			}
			return fromBalance, toBalance, nil
		}
		return nil, nil, err
	}

	if err := tx.Commit(); err != nil {
		return nil, nil, err
	}
	fromBalance, err := s.GetBalance(ctx, serviceID, fromUserHash)
	if err != nil {
		return nil, nil, err
	}
	toBalance, err := s.GetBalance(ctx, serviceID, toUserHash)
	if err != nil {
		return nil, nil, err
	}
	return fromBalance, toBalance, nil
}

// Credit adds USDT to a user's balance and records the transaction.
func (s *BalanceService) Credit(ctx context.Context, serviceID, userHash string, amountUSDT float64, txType model.TxType, description string) error {
	if err := s.ensureBillingUser(ctx, userHash); err != nil {
		return err
	}
	rate, _ := s.exchangeRepo.GetRate(ctx, "USDT", "RUB")
	var rubRate, amountRUB float64
	if rate != nil {
		rubRate = rate.Rate
		amountRUB = amountUSDT * rubRate
	}

	opts := &sql.TxOptions{Isolation: sql.LevelSerializable}
	tx, err := s.db.BeginTxx(ctx, opts)
	if err != nil {
		return err
	}
	defer tx.Rollback()

	_, err = tx.ExecContext(ctx,
		`INSERT INTO service_balances (id, service_id, user_hash, balance_usdt, updated_at)
		 VALUES ($1, $2, $3, $4, $5)
		 ON CONFLICT (service_id, user_hash) DO NOTHING`,
		uuid.NewString(), serviceID, userHash, 0.0, time.Now(),
	)
	if err != nil {
		return err
	}

	var currentBalance float64
	err = tx.QueryRowContext(ctx,
		`SELECT balance_usdt FROM service_balances WHERE service_id = $1 AND user_hash = $2 FOR UPDATE`,
		serviceID, userHash,
	).Scan(&currentBalance)
	if err != nil {
		return err
	}

	if currentBalance+amountUSDT < 0 {
		return ErrInsufficientFunds
	}

	_, err = tx.ExecContext(ctx,
		`UPDATE service_balances
		 SET balance_usdt = balance_usdt + $1, updated_at = NOW()
		 WHERE service_id = $2 AND user_hash = $3`,
		amountUSDT, serviceID, userHash,
	)
	if err != nil {
		return err
	}

	_, err = tx.ExecContext(ctx,
		`INSERT INTO transactions (id, service_id, user_hash, operation_id, type, amount_usdt, amount_rub, rate, description, created_at)
		 VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
		uuid.NewString(), serviceID, userHash, "", txType, amountUSDT, amountRUB, rubRate, description, time.Now(),
	)
	if err != nil {
		return err
	}

	return tx.Commit()
}

func (s *BalanceService) History(ctx context.Context, serviceID, userHash string, limit, offset int) ([]model.Transaction, error) {
	return s.txRepo.ListByUser(ctx, serviceID, userHash, limit, offset)
}

func (s *BalanceService) ensureBillingUser(ctx context.Context, userHash string) error {
	_, err := s.userRepo.Upsert(ctx, userHash)
	return err
}

func isSupportedTxType(txType model.TxType) bool {
	switch txType {
	case model.TxTopup, model.TxTransfer, model.TxWithdraw:
		return true
	default:
		return false
	}
}

func isDuplicateOperationError(err error) bool {
	pqError, ok := err.(*pq.Error)
	return ok && pqError.Code == "23505"
}
