package service

import (
	"context"
	"encoding/json"
	"time"

	"github.com/cerber/billing/internal/model"
	"github.com/cerber/billing/internal/repository"
	"github.com/google/uuid"
)

type PaymentService struct {
	paymentRepo *repository.PaymentRepo
	balanceSvc  *BalanceService
}

func NewPaymentService(paymentRepo *repository.PaymentRepo, balanceSvc *BalanceService) *PaymentService {
	return &PaymentService{paymentRepo: paymentRepo, balanceSvc: balanceSvc}
}

type Requisites struct {
	CardNumber string `json:"card_number,omitempty"`
	Bank       string `json:"bank,omitempty"`
	Wallet     string `json:"wallet,omitempty"`
	IBAN       string `json:"iban,omitempty"`
}

// CreatePayment initialises an incoming payment and returns requisites for the payer.
func (s *PaymentService) CreatePayment(ctx context.Context, serviceID, providerID, accountID, currency string, amount float64, req Requisites) (*model.Payment, error) {
	raw, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	p := &model.Payment{
		ID:         uuid.NewString(),
		ServiceID:  serviceID,
		ProviderID: providerID,
		AccountID:  accountID,
		ExternalID: uuid.NewString(),
		Amount:     amount,
		Currency:   currency,
		Status:     model.PaymentPending,
		Requisites: string(raw),
		CreatedAt:  time.Now(),
		UpdatedAt:  time.Now(),
	}
	return p, s.paymentRepo.Create(ctx, p)
}

// GetRequisites returns requisites for an existing payment.
func (s *PaymentService) GetRequisites(ctx context.Context, paymentID string) (Requisites, error) {
	p, err := s.paymentRepo.FindByID(ctx, paymentID)
	if err != nil {
		return Requisites{}, err
	}
	var req Requisites
	err = json.Unmarshal([]byte(p.Requisites), &req)
	return req, err
}

// CheckPayment verifies payment and, if confirmed, credits the account balance.
func (s *PaymentService) CheckPayment(ctx context.Context, paymentID string) (*model.Payment, error) {
	p, err := s.paymentRepo.FindByID(ctx, paymentID)
	if err != nil {
		return nil, err
	}
	if p.Status != model.PaymentPending {
		return p, nil
	}
	// In a real system you'd call the provider's API here.
	// We simulate auto-confirm for demo purposes.
	if err = s.paymentRepo.UpdateStatus(ctx, paymentID, model.PaymentConfirmed); err != nil {
		return nil, err
	}
	p.Status = model.PaymentConfirmed
	if _, err = s.balanceSvc.Deposit(ctx, p.AccountID, p.Amount, "payment "+paymentID); err != nil {
		return nil, err
	}
	return p, nil
}

// GetStatus returns the current status of a payment.
func (s *PaymentService) GetStatus(ctx context.Context, paymentID string) (model.PaymentStatus, error) {
	p, err := s.paymentRepo.FindByID(ctx, paymentID)
	if err != nil {
		return "", err
	}
	return p.Status, nil
}

// List returns payments for a service.
func (s *PaymentService) List(ctx context.Context, serviceID string, limit, offset int) ([]model.Payment, error) {
	return s.paymentRepo.ListByService(ctx, serviceID, limit, offset)
}
