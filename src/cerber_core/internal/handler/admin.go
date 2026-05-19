package handler

import (
	"errors"
	"net/http"

	"github.com/cerber/billing/internal/model"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

// AdminHandler handles privileged operations (service creation).
type AdminHandler struct {
	authSvc    *service.AuthService
	balanceSvc *service.BalanceService
	topupSvc   *service.TopupService
}

func NewAdminHandler(authSvc *service.AuthService, balanceSvc *service.BalanceService, topupSvc *service.TopupService) *AdminHandler {
	return &AdminHandler{authSvc: authSvc, balanceSvc: balanceSvc, topupSvc: topupSvc}
}

// CreateService provisions a new API consumer with api_key + secret_key.
// The raw values are returned ONCE — they are not recoverable after this response.
// Protected by X-Admin-Key header.
func (h *AdminHandler) CreateService(c *gin.Context) {
	var req struct {
		Name string `json:"name" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	svc, rawAPIKey, rawSecretKey, err := h.authSvc.CreateService(c.Request.Context(), req.Name)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "could not create service"})
		return
	}
	// Raw keys are shown ONCE — never stored in plaintext.
	c.JSON(http.StatusCreated, gin.H{
		"id":         svc.ID,
		"name":       svc.Name,
		"api_key":    rawAPIKey,
		"secret_key": rawSecretKey,
		"note":       "Store api_key and secret_key securely — they will not be shown again.",
	})
}

func (h *AdminHandler) AdjustBalance(c *gin.Context) {
	var req struct {
		ServiceID   string  `json:"service_id" binding:"required"`
		UserHash    string  `json:"user_hash" binding:"required"`
		DeltaUSDT   float64 `json:"delta_usdt" binding:"required"`
		TxType      string  `json:"tx_type" binding:"required"`
		Description string  `json:"description"`
		OperationID string  `json:"operation_id" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	result, err := h.balanceSvc.Adjust(
		c.Request.Context(),
		req.ServiceID,
		req.UserHash,
		req.DeltaUSDT,
		model.TxType(req.TxType),
		req.Description,
		req.OperationID,
	)
	if err != nil {
		status := http.StatusInternalServerError
		if errors.Is(err, service.ErrInsufficientFunds) {
			status = http.StatusConflict
		}
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, result)
}

func (h *AdminHandler) ConfirmPayment(c *gin.Context) {
	paymentID := c.Param("payment_id")
	if paymentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "payment_id is required"})
		return
	}
	session, err := h.topupSvc.Confirm(c.Request.Context(), paymentID)
	if err != nil {
		status := mapPaymentErrorToStatus(err)
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, session)
}

func (h *AdminHandler) FailPayment(c *gin.Context) {
	paymentID := c.Param("payment_id")
	if paymentID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "payment_id is required"})
		return
	}
	session, err := h.topupSvc.Fail(c.Request.Context(), paymentID)
	if err != nil {
		status := mapPaymentErrorToStatus(err)
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, session)
}
