package service

import (
	"context"
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

	tx, err := s.db.BeginTxx(ctx, nil)
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

	result, err := tx.ExecContext(ctx,
		`UPDATE service_balances
		 SET balance_usdt = balance_usdt + $1, updated_at = NOW()
		 WHERE service_id = $2 AND user_hash = $3 AND balance_usdt + $1 >= 0`,
		deltaUSDT, serviceID, userHash,
	)
	if err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	rowsAffected, err := result.RowsAffected()
	if err != nil {
		_ = tx.Rollback()
		return nil, err
	}
	if rowsAffected == 0 {
		_ = tx.Rollback()
		return nil, ErrInsufficientFunds
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

// Credit adds USDT to a user's balance and records the transaction.
func (s *BalanceService) Credit(ctx context.Context, serviceID, userHash string, amountUSDT float64, txType model.TxType, description string) error {
	if err := s.ensureBillingUser(ctx, userHash); err != nil {
		return err
	}
	// Ensure user has a balance row
	if _, err := s.balanceRepo.FindOrCreate(ctx, serviceID, userHash); err != nil {
		return err
	}
	if err := s.balanceRepo.AddUSDT(ctx, serviceID, userHash, amountUSDT); err != nil {
		return err
	}

	rate, _ := s.exchangeRepo.GetRate(ctx, "USDT", "RUB")
	var rubRate, amountRUB float64
	if rate != nil {
		rubRate = rate.Rate
		amountRUB = amountUSDT * rubRate
	}

	t := &model.Transaction{
		ID:          uuid.NewString(),
		ServiceID:   serviceID,
		UserHash:    userHash,
		OperationID: "",
		Type:        txType,
		AmountUSDT:  amountUSDT,
		AmountRUB:   amountRUB,
		Rate:        rubRate,
		Description: description,
		CreatedAt:   time.Now(),
	}
	return s.txRepo.Create(ctx, t)
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
