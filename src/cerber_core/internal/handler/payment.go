package handler

import (
	"errors"
	"net/http"
	"strings"

	"github.com/cerber/billing/internal/middleware"
	"github.com/cerber/billing/internal/model"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

type TopupHandler struct {
	topupSvc *service.TopupService
}

type createPaymentRequest struct {
	EncryptedUserHash string  `json:"encrypted_user_hash" binding:"required"`
	MethodID          string  `json:"method_id"`
	PaymentMethodID   string  `json:"payment_method_id"`
	AmountUSDT        float64 `json:"amount_usdt" binding:"required,gt=0"`
}

type paymentWebhookRequest struct {
	PaymentID string `json:"payment_id" binding:"required"`
	Status    string `json:"status" binding:"required"`
}

type refundPaymentRequest struct {
	PaymentID   string `json:"payment_id" binding:"required"`
	OperationID string `json:"operation_id" binding:"required"`
	Description string `json:"description"`
}

func NewTopupHandler(topupSvc *service.TopupService) *TopupHandler {
	return &TopupHandler{topupSvc: topupSvc}
}

// ListMethods returns all active deposit gateways with their fee structure.
func (h *TopupHandler) ListMethods(c *gin.Context) {
	svc := middleware.GetService(c)
	methods, err := h.topupSvc.ListMethods(c.Request.Context())
	if err != nil {
		EncryptedJSON(c, http.StatusInternalServerError, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, methods, svc.SecretKey)
}

// Create initiates a top-up session and returns payment requisites.
// Body: { "encrypted_user_hash": "...", "method_id": "...", "amount_usdt": 50.0 }
func (h *TopupHandler) Create(c *gin.Context) {
	svc := middleware.GetService(c)
	var req createPaymentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	methodID := req.MethodID
	if methodID == "" {
		methodID = req.PaymentMethodID
	}
	if methodID == "" {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": "method_id or payment_method_id is required"}, svc.SecretKey)
		return
	}
	userHash, err := service.DecryptUserHash(req.EncryptedUserHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	session, err := h.topupSvc.CreateSession(c.Request.Context(), svc.ID, userHash, methodID, req.AmountUSDT)
	if err != nil {
		EncryptedJSON(c, http.StatusInternalServerError, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusCreated, session, svc.SecretKey)
}

// Status returns the current status of a top-up session.
// Query param: session_id=<uuid>
func (h *TopupHandler) Status(c *gin.Context) {
	svc := middleware.GetService(c)
	sessionID := c.Query("session_id")
	if sessionID == "" {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": "session_id is required"}, svc.SecretKey)
		return
	}
	session, err := h.topupSvc.GetStatus(c.Request.Context(), sessionID)
	if err != nil {
		EncryptedJSON(c, mapPaymentErrorToStatus(err), gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, gin.H{
		"session_id":  session.ID,
		"status":      session.Status,
		"amount_usdt": session.AmountUSDT,
		"amount_rub":  session.AmountRUB,
		"updated_at":  session.UpdatedAt,
	}, svc.SecretKey)
}

// Confirm marks a top-up session as confirmed and credits the balance idempotently.
// Body: { "session_id": "uuid" }
func (h *TopupHandler) Confirm(c *gin.Context) {
	svc := middleware.GetService(c)
	var req struct {
		SessionID string `json:"session_id" binding:"required"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	session, err := h.topupSvc.Confirm(c.Request.Context(), req.SessionID)
	if err != nil {
		EncryptedJSON(c, mapPaymentErrorToStatus(err), gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, session, svc.SecretKey)
}

func (h *TopupHandler) CreatePayment(c *gin.Context) {
	h.Create(c)
}

func (h *TopupHandler) PaymentStatus(c *gin.Context) {
	svc := middleware.GetService(c)
	paymentID := c.Query("payment_id")
	if paymentID == "" {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": "payment_id is required"}, svc.SecretKey)
		return
	}
	session, err := h.topupSvc.GetStatus(c.Request.Context(), paymentID)
	if err != nil {
		EncryptedJSON(c, mapPaymentErrorToStatus(err), gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, gin.H{
		"payment_id":  session.ID,
		"status":      session.Status,
		"amount_usdt": session.AmountUSDT,
		"amount_rub":  session.AmountRUB,
		"payment_url": session.PaymentURL,
		"updated_at":  session.UpdatedAt,
		"service_id":  session.ServiceID,
		"method_id":   session.MethodID,
		"requisites":  session.Requisites,
	}, svc.SecretKey)
}

func (h *TopupHandler) Webhook(c *gin.Context) {
	svc := middleware.GetService(c)
	var req paymentWebhookRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	status := model.TopupStatus(req.Status)
	session, err := h.topupSvc.HandleWebhook(c.Request.Context(), req.PaymentID, status)
	if err != nil {
		EncryptedJSON(c, mapPaymentErrorToStatus(err), gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, gin.H{
		"payment_id": session.ID,
		"status":     session.Status,
	}, svc.SecretKey)
}

func (h *TopupHandler) Refund(c *gin.Context) {
	svc := middleware.GetService(c)
	var req refundPaymentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	description := req.Description
	if description == "" {
		description = "payment refund"
	}
	session, err := h.topupSvc.Refund(c.Request.Context(), req.PaymentID, req.OperationID, description)
	if err != nil {
		EncryptedJSON(c, mapPaymentErrorToStatus(err), gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, gin.H{
		"payment_id":   session.ID,
		"status":       "refunded",
		"operation_id": req.OperationID,
	}, svc.SecretKey)
}

func mapPaymentErrorToStatus(err error) int {
	if errors.Is(err, service.ErrTopupNotFound) {
		return http.StatusNotFound
	}
	if errors.Is(err, service.ErrInsufficientFunds) {
		return http.StatusConflict
	}
	if strings.Contains(err.Error(), "unsupported") ||
		strings.Contains(err.Error(), "required") ||
		strings.Contains(err.Error(), "cannot") ||
		strings.Contains(err.Error(), "only") {
		return http.StatusBadRequest
	}
	return http.StatusInternalServerError
}
