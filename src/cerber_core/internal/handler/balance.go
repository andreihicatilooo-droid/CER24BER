package handler

import (
	"net/http"

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
