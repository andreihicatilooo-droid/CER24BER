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
