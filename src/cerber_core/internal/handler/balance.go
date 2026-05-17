package handler

import (
	"net/http"
	"strconv"

	"github.com/cerber/billing/internal/middleware"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

type BalanceHandler struct {
	balanceSvc *service.BalanceService
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
