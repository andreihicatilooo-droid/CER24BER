package service

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/cerber/billing/internal/model"
	"github.com/cerber/billing/internal/repository"
	"github.com/google/uuid"
)

type TopupService struct {
	topupRepo   *repository.TopupRepo
	balanceSvc  *BalanceService
	exchangeRepo *repository.ExchangeRepo
}

func NewTopupService(topupRepo *repository.TopupRepo, balanceSvc *BalanceService, exchangeRepo *repository.ExchangeRepo) *TopupService {
	return &TopupService{topupRepo: topupRepo, balanceSvc: balanceSvc, exchangeRepo: exchangeRepo}
}

// ListMethods returns all active deposit methods.
func (s *TopupService) ListMethods(ctx context.Context) ([]model.TopupMethod, error) {
	return s.topupRepo.ListMethods(ctx)
}

// CreateSession initiates a top-up and returns the session with payment requisites.
func (s *TopupService) CreateSession(ctx context.Context, serviceID, userHash, methodID string, amountUSDT float64) (*model.TopupSession, error) {
	rate, err := s.exchangeRepo.GetRate(ctx, "USDT", "RUB")
	if err != nil {
		return nil, err
	}

	amountRUB := amountUSDT * rate.Rate

	// In production: call the provider's API to get real requisites / payment URL.
	// Here we generate placeholder requisites.
	requisites := map[string]string{
		"account":    fmt.Sprintf("4276%010d", time.Now().UnixNano()%10000000000),
		"bank":       "CerberBank",
		"amount_rub": fmt.Sprintf("%.2f", amountRUB),
		"comment":    "Pay " + uuid.NewString()[:8],
	}
	reqJSON, _ := json.Marshal(requisites)

	session := &model.TopupSession{
		ID:         uuid.NewString(),
		ServiceID:  serviceID,
		UserHash:   userHash,
		MethodID:   methodID,
		AmountUSDT: amountUSDT,
		AmountRUB:  amountRUB,
		Rate:       rate.Rate,
		Status:     model.TopupPending,
		PaymentURL: "",
		Requisites: string(reqJSON),
		CreatedAt:  time.Now(),
		UpdatedAt:  time.Now(),
	}
	if err = s.topupRepo.CreateSession(ctx, session); err != nil {
		return nil, err
	}
	return session, nil
}

// GetStatus returns the current status of a top-up session.
func (s *TopupService) GetStatus(ctx context.Context, sessionID string) (*model.TopupSession, error) {
	return s.topupRepo.FindSessionByID(ctx, sessionID)
}

// Confirm is called by a webhook / manual check to credit the user balance.
func (s *TopupService) Confirm(ctx context.Context, sessionID string) (*model.TopupSession, error) {
	session, err := s.topupRepo.FindSessionByID(ctx, sessionID)
	if err != nil {
		return nil, err
	}
	if session.Status != model.TopupPending {
		return session, nil // idempotent
	}
	if err = s.topupRepo.UpdateSessionStatus(ctx, sessionID, model.TopupConfirmed); err != nil {
		return nil, err
	}
	session.Status = model.TopupConfirmed
	if err = s.balanceSvc.Credit(ctx, session.ServiceID, session.UserHash,
		session.AmountUSDT, model.TxTopup, "topup:" +sessionID); err != nil {
		return nil, err
	}
	return session, nil
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
