package service

import (
	"context"
	"encoding/base64"
	"errors"
	"time"

	"github.com/cerber/billing/internal/crypto"
	"github.com/cerber/billing/internal/model"
	"github.com/cerber/billing/internal/repository"
	"github.com/google/uuid"
)

// AuthService manages service registration and API-key validation.
type AuthService struct {
	serviceRepo   *repository.ServiceRepo
	masterAESKey  []byte
	masterHMACKey []byte
}

func NewAuthService(serviceRepo *repository.ServiceRepo, masterAESKey, masterHMACKey []byte) *AuthService {
	return &AuthService{
		serviceRepo:   serviceRepo,
		masterAESKey:  masterAESKey,
		masterHMACKey: masterHMACKey,
	}
}

// CreateService generates a new service with a random API key and AES-256 secret key.
// Returns the service (persisted), raw API key, and raw secret key — the raw values
// are only returned once and must be stored securely by the caller.
func (s *AuthService) CreateService(ctx context.Context, name string) (svc *model.Service, rawAPIKey, rawSecretKey string, err error) {
	// Generate 32-byte raw API key
	apiKeyBytes, err := crypto.GenerateKey(32)
	if err != nil {
		return nil, "", "", err
	}
	rawAPIKey = base64.StdEncoding.EncodeToString(apiKeyBytes)

	// Generate 32-byte AES service secret key
	secretKeyBytes, err := crypto.GenerateKey(32)
	if err != nil {
		return nil, "", "", err
	}
	rawSecretKey = base64.StdEncoding.EncodeToString(secretKeyBytes)

	// Hash the API key with HMAC-SHA256 (deterministic, no salt — master key is the secret)
	apiKeyHash := crypto.HMACHash([]byte(rawAPIKey), s.masterHMACKey)

	// Encrypt the service secret key with the master AES key
	secretKeyEncrypted, err := crypto.Encrypt(s.masterAESKey, secretKeyBytes)
	if err != nil {
		return nil, "", "", err
	}

	svc = &model.Service{
		ID:                 uuid.NewString(),
		Name:               name,
		APIKeyHash:         apiKeyHash,
		SecretKeyEncrypted: secretKeyEncrypted,
		IsActive:           true,
		CreatedAt:          time.Now(),
	}
	if err = s.serviceRepo.Create(ctx, svc); err != nil {
		return nil, "", "", err
	}
	return svc, rawAPIKey, rawSecretKey, nil
}

// ValidateAPIKey looks up the service for a raw API key and decrypts its secret key.
// Returns the service with SecretKey populated (transient field).
func (s *AuthService) ValidateAPIKey(ctx context.Context, rawAPIKey string) (*model.Service, error) {
	hash := crypto.HMACHash([]byte(rawAPIKey), s.masterHMACKey)
	svc, err := s.serviceRepo.FindByAPIKeyHash(ctx, hash)
	if err != nil {
		return nil, errors.New("unauthorized")
	}
	// Decrypt the service's own AES secret key
	secretKeyBytes, err := crypto.Decrypt(s.masterAESKey, svc.SecretKeyEncrypted)
	if err != nil {
		return nil, errors.New("internal: cannot decrypt service key")
	}
	svc.SecretKey = secretKeyBytes
	return svc, nil
}

// DecryptUserHash decrypts an encrypted_user_hash sent by a client.
func DecryptUserHash(encryptedHash string, serviceKey []byte) (string, error) {
	if encryptedHash == "" {
		return "", errors.New("encrypted_user_hash is required")
	}
	raw, err := crypto.Decrypt(serviceKey, encryptedHash)
	if err != nil {
		return "", errors.New("cannot decrypt user hash: " + err.Error())
	}
	return string(raw), nil
}
