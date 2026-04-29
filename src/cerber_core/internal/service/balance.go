package service

import (
	"context"
	"time"

	"github.com/cerber/billing/internal/model"
	"github.com/cerber/billing/internal/repository"
	"github.com/google/uuid"
)

type BalanceService struct {
	balanceRepo  *repository.BalanceRepo
	txRepo       *repository.TransactionRepo
	exchangeRepo *repository.ExchangeRepo
}

func NewBalanceService(
	balanceRepo *repository.BalanceRepo,
	txRepo *repository.TransactionRepo,
	exchangeRepo *repository.ExchangeRepo,
) *BalanceService {
	return &BalanceService{balanceRepo: balanceRepo, txRepo: txRepo, exchangeRepo: exchangeRepo}
}

type BalanceResult struct {
	BalanceUSDT float64 `json:"balance_usdt"`
	BalanceRUB  float64 `json:"balance_rub"`
	Rate        float64 `json:"rate_usdt_rub"`
}

// GetBalance returns the user's USDT balance and RUB equivalent.
func (s *BalanceService) GetBalance(ctx context.Context, serviceID, userHash string) (*BalanceResult, error) {
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

// Credit adds USDT to a user's balance and records the transaction.
func (s *BalanceService) Credit(ctx context.Context, serviceID, userHash string, amountUSDT float64, txType model.TxType, description string) error {
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
		Type:        txType,
		AmountUSDT:  amountUSDT,
		AmountRUB:   amountRUB,
		Rate:        rubRate,
		Description: description,
		CreatedAt:   time.Now(),
	}
	return s.txRepo.Create(ctx, t)
}

func (s *BalanceService) History(ctx context.Context, accountID string, limit, offset int) ([]model.Transaction, error) {
	return s.txRepo.ListByAccount(ctx, accountID, limit, offset)
}
