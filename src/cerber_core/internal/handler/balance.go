package handler

import (
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/cerber/billing/internal/middleware"
	"github.com/cerber/billing/internal/model"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

type BalanceHandler struct {
	balanceSvc *service.BalanceService
}

type adjustBalanceRequest struct {
	EncryptedUserHash string  `json:"encrypted_user_hash" binding:"required"`
	DeltaUSDT         float64 `json:"delta_usdt" binding:"required"`
	TxType            string  `json:"tx_type" binding:"required"`
	Description       string  `json:"description"`
	OperationID       string  `json:"operation_id" binding:"required"`
}

type holdRequest struct {
	EncryptedUserHash string  `json:"encrypted_user_hash" binding:"required"`
	AmountUSDT        float64 `json:"amount_usdt" binding:"required,gt=0"`
	Description       string  `json:"description"`
	OperationID       string  `json:"operation_id" binding:"required"`
}

type transferRequest struct {
	FromEncryptedUserHash string  `json:"from_encrypted_user_hash" binding:"required"`
	ToEncryptedUserHash   string  `json:"to_encrypted_user_hash" binding:"required"`
	AmountUSDT            float64 `json:"amount_usdt" binding:"required,gt=0"`
	Description           string  `json:"description"`
	OperationID           string  `json:"operation_id" binding:"required"`
}

func NewBalanceHandler(balanceSvc *service.BalanceService) *BalanceHandler {
	return &BalanceHandler{balanceSvc: balanceSvc}
}

// Get returns the user's USDT balance and its RUB equivalent.
// Query param: encrypted_user_hash=<Base64 AES-GCM>
func (h *BalanceHandler) Get(c *gin.Context) {
	svc := middleware.GetService(c)
	encHash := c.Query("encrypted_user_hash")
	userHash, err := service.DecryptUserHash(encHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	result, err := h.balanceSvc.GetBalance(c.Request.Context(), svc.ID, userHash)
	if err != nil {
		EncryptedJSON(c, http.StatusInternalServerError, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, result, svc.SecretKey)
}

// History returns paginated transaction history for the user within service scope.
// Query params: encrypted_user_hash=<Base64 AES-GCM>, limit=<int>, offset=<int>
func (h *BalanceHandler) History(c *gin.Context) {
	svc := middleware.GetService(c)
	encHash := c.Query("encrypted_user_hash")
	userHash, err := service.DecryptUserHash(encHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}

	limit := 20
	if raw := c.Query("limit"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 1 || parsed > 100 {
			EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": "limit must be between 1 and 100"}, svc.SecretKey)
			return
		}
		limit = parsed
	}

	offset := 0
	if raw := c.Query("offset"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 0 {
			EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": "offset must be >= 0"}, svc.SecretKey)
			return
		}
		offset = parsed
	}

	transactions, err := h.balanceSvc.History(c.Request.Context(), svc.ID, userHash, limit, offset)
	if err != nil {
		EncryptedJSON(c, http.StatusInternalServerError, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, transactions, svc.SecretKey)
}

// Adjust applies an idempotent balance mutation in USDT and returns the current balance.
// Body: { "encrypted_user_hash": "...", "delta_usdt": 10.0, "tx_type": "topup", "description": "...", "operation_id": "..." }
func (h *BalanceHandler) Adjust(c *gin.Context) {
	svc := middleware.GetService(c)
	var req adjustBalanceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	if req.DeltaUSDT == 0 {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": "delta_usdt must not be zero"}, svc.SecretKey)
		return
	}
	userHash, err := service.DecryptUserHash(req.EncryptedUserHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}

	result, err := h.balanceSvc.Adjust(
		c.Request.Context(),
		svc.ID,
		userHash,
		req.DeltaUSDT,
		model.TxType(req.TxType),
		req.Description,
		req.OperationID,
	)
	if err != nil {
		status := mapBalanceErrorToStatus(err)
		EncryptedJSON(c, status, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, result, svc.SecretKey)
}

func (h *BalanceHandler) Hold(c *gin.Context) {
	svc := middleware.GetService(c)
	var req holdRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	userHash, err := service.DecryptUserHash(req.EncryptedUserHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	result, err := h.balanceSvc.Hold(c.Request.Context(), svc.ID, userHash, req.AmountUSDT, req.Description, req.OperationID)
	if err != nil {
		EncryptedJSON(c, mapBalanceErrorToStatus(err), gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, result, svc.SecretKey)
}

func (h *BalanceHandler) Unblock(c *gin.Context) {
	svc := middleware.GetService(c)
	var req holdRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	userHash, err := service.DecryptUserHash(req.EncryptedUserHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	result, err := h.balanceSvc.Unblock(c.Request.Context(), svc.ID, userHash, req.AmountUSDT, req.Description, req.OperationID)
	if err != nil {
		EncryptedJSON(c, mapBalanceErrorToStatus(err), gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, result, svc.SecretKey)
}

func (h *BalanceHandler) Transfer(c *gin.Context) {
	svc := middleware.GetService(c)
	var req transferRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	fromHash, err := service.DecryptUserHash(req.FromEncryptedUserHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	toHash, err := service.DecryptUserHash(req.ToEncryptedUserHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	fromBalance, toBalance, err := h.balanceSvc.Transfer(c.Request.Context(), svc.ID, fromHash, toHash, req.AmountUSDT, req.Description, req.OperationID)
	if err != nil {
		EncryptedJSON(c, mapBalanceErrorToStatus(err), gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, gin.H{
		"from": fromBalance,
		"to":   toBalance,
	}, svc.SecretKey)
}

func (h *BalanceHandler) CreateWithdrawal(c *gin.Context) {
	svc := middleware.GetService(c)
	var req holdRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	userHash, err := service.DecryptUserHash(req.EncryptedUserHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	result, err := h.balanceSvc.CreateWithdrawal(c.Request.Context(), svc.ID, userHash, req.AmountUSDT, req.Description, req.OperationID)
	if err != nil {
		EncryptedJSON(c, mapBalanceErrorToStatus(err), gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusCreated, gin.H{
		"operation_id": req.OperationID,
		"status":       "completed",
		"balance":      result,
	}, svc.SecretKey)
}

func (h *BalanceHandler) CancelWithdrawal(c *gin.Context) {
	svc := middleware.GetService(c)
	var req holdRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	userHash, err := service.DecryptUserHash(req.EncryptedUserHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	result, err := h.balanceSvc.CancelWithdrawal(c.Request.Context(), svc.ID, userHash, req.AmountUSDT, req.Description, req.OperationID)
	if err != nil {
		EncryptedJSON(c, mapBalanceErrorToStatus(err), gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, gin.H{
		"operation_id": req.OperationID,
		"status":       "cancelled",
		"balance":      result,
	}, svc.SecretKey)
}

func mapBalanceErrorToStatus(err error) int {
	if errors.Is(err, service.ErrInsufficientFunds) {
		return http.StatusConflict
	}
	if strings.Contains(err.Error(), "required") ||
		strings.Contains(err.Error(), "unsupported") ||
		strings.Contains(err.Error(), "must be") ||
		strings.Contains(err.Error(), "differ") {
		return http.StatusBadRequest
	}
	return http.StatusInternalServerError
}
