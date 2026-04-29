package service

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"time"

	"github.com/cerber/billing/internal/model"
	"github.com/cerber/billing/internal/repository"
	"github.com/google/uuid"
	"golang.org/x/crypto/bcrypt"
)

type AuthService struct {
	userRepo    *repository.UserRepo
	serviceRepo *repository.ServiceRepo
	jwtSecret   string
}

func NewAuthService(userRepo *repository.UserRepo, serviceRepo *repository.ServiceRepo, jwtSecret string) *AuthService {
	return &AuthService{userRepo: userRepo, serviceRepo: serviceRepo, jwtSecret: jwtSecret}
}

func (s *AuthService) RegisterUser(ctx context.Context, email, password string) (*model.User, error) {
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return nil, err
	}
	u := &model.User{
		ID:           uuid.NewString(),
		Email:        email,
		PasswordHash: string(hash),
		CreatedAt:    time.Now(),
	}
	if err := s.userRepo.Create(ctx, u); err != nil {
		return nil, err
	}
	return u, nil
}

func (s *AuthService) LoginUser(ctx context.Context, email, password string) (string, error) {
	u, err := s.userRepo.FindByEmail(ctx, email)
	if err != nil {
		return "", errors.New("invalid credentials")
	}
	if err := bcrypt.CompareHashAndPassword([]byte(u.PasswordHash), []byte(password)); err != nil {
		return "", errors.New("invalid credentials")
	}
	return GenerateJWT(u.ID, s.jwtSecret)
}

// CreateService generates a new service with API key + secret.
func (s *AuthService) CreateService(ctx context.Context, name string) (*model.Service, string, error) {
	apiKey, err := randomHex(16)
	if err != nil {
		return nil, "", err
	}
	rawSecret, err := randomHex(32)
	if err != nil {
		return nil, "", err
	}
	secretHash, err := bcrypt.GenerateFromPassword([]byte(rawSecret), bcrypt.DefaultCost)
	if err != nil {
		return nil, "", err
	}
	svc := &model.Service{
		ID:        uuid.NewString(),
		Name:      name,
		APIKey:    apiKey,
		APISecret: string(secretHash),
		Active:    true,
		CreatedAt: time.Now(),
	}
	if err := s.serviceRepo.Create(ctx, svc); err != nil {
		return nil, "", err
	}
	return svc, rawSecret, nil
}

func randomHex(n int) (string, error) {
	b := make([]byte, n)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}
