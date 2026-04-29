package service

import (
	"context"
	"database/sql"
	"time"

	"github.com/cerber/billing/internal/model"
	"github.com/cerber/billing/internal/repository"
	"github.com/google/uuid"
	"github.com/jmoiron/sqlx"
)

type BalanceService struct {
	db          *sqlx.DB
	accountRepo *repository.AccountRepo
	txRepo      *repository.TransactionRepo
}

func NewBalanceService(db *sqlx.DB, accountRepo *repository.AccountRepo, txRepo *repository.TransactionRepo) *BalanceService {
	return &BalanceService{db: db, accountRepo: accountRepo, txRepo: txRepo}
}

func (s *BalanceService) CreateAccount(ctx context.Context, userID, name, currency string) (*model.Account, error) {
	a := &model.Account{
		ID:        uuid.NewString(),
		UserID:    userID,
		Name:      name,
		Currency:  currency,
		Balance:   0,
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}
	return a, s.accountRepo.Create(ctx, a)
}

func (s *BalanceService) GetBalance(ctx context.Context, accountID string) (*model.Account, error) {
	return s.accountRepo.FindByID(ctx, accountID)
}

func (s *BalanceService) GetBalancesByUser(ctx context.Context, userID string) ([]model.Account, error) {
	return s.accountRepo.FindByUserID(ctx, userID)
}

func (s *BalanceService) GetBalanceByProvider(ctx context.Context, providerID string) ([]model.Account, error) {
	return s.accountRepo.FindByProvider(ctx, providerID)
}

func (s *BalanceService) GetTotalBalance(ctx context.Context, currency string) (float64, error) {
	return s.accountRepo.TotalBalance(ctx, currency)
}

func (s *BalanceService) Deposit(ctx context.Context, accountID string, amount float64, description string) (*model.Transaction, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	defer func() {
		if err != nil {
			_ = tx.Rollback()
		}
	}()

	if err = s.accountRepo.UpdateBalance(ctx, tx, accountID, amount); err != nil {
		return nil, err
	}

	t := &model.Transaction{
		ID:          uuid.NewString(),
		ToAccountID: &accountID,
		Amount:      amount,
		Type:        model.TxDeposit,
		Description: description,
		CreatedAt:   time.Now(),
	}
	if err = s.txRepo.Create(ctx, t); err != nil {
		return nil, err
	}
	return t, tx.Commit()
}

func (s *BalanceService) Withdraw(ctx context.Context, accountID string, amount float64, description string) (*model.Transaction, error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, err
	}
	defer func() {
		if err != nil {
			_ = tx.Rollback()
		}
	}()

	if err = s.accountRepo.UpdateBalance(ctx, tx, accountID, -amount); err != nil {
		return nil, err
	}

	t := &model.Transaction{
		ID:            uuid.NewString(),
		FromAccountID: &accountID,
		Amount:        amount,
		Type:          model.TxWithdrawal,
		Description:   description,
		CreatedAt:     time.Now(),
	}
	if err = s.txRepo.Create(ctx, t); err != nil {
		return nil, err
	}
	return t, tx.Commit()
}

func (s *BalanceService) Transfer(ctx context.Context, fromID, toID string, amount float64, description string) (*model.Transaction, error) {
	tx, err := s.db.BeginTx(ctx, &sql.TxOptions{Isolation: sql.LevelSerializable})
	if err != nil {
		return nil, err
	}
	defer func() {
		if err != nil {
			_ = tx.Rollback()
		}
	}()

	if err = s.accountRepo.UpdateBalance(ctx, tx, fromID, -amount); err != nil {
		return nil, err
	}
	if err = s.accountRepo.UpdateBalance(ctx, tx, toID, amount); err != nil {
		return nil, err
	}

	t := &model.Transaction{
		ID:            uuid.NewString(),
		FromAccountID: &fromID,
		ToAccountID:   &toID,
		Amount:        amount,
		Type:          model.TxTransfer,
		Description:   description,
		CreatedAt:     time.Now(),
	}
	if err = s.txRepo.Create(ctx, t); err != nil {
		return nil, err
	}
	return t, tx.Commit()
}

func (s *BalanceService) History(ctx context.Context, accountID string, limit, offset int) ([]model.Transaction, error) {
	return s.txRepo.ListByAccount(ctx, accountID, limit, offset)
}
