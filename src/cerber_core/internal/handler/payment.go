package handler

import (
	"net/http"
	"strconv"

	"github.com/cerber/billing/internal/middleware"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

type PaymentHandler struct {
	paymentSvc *service.PaymentService
}

func NewPaymentHandler(paymentSvc *service.PaymentService) *PaymentHandler {
	return &PaymentHandler{paymentSvc: paymentSvc}
}

// @Summary List available deposit providers/methods
// @Tags deposit
// @Security ApiKeyAuth
// @Produce json
// @Success 200 {array} map[string]string
// @Router /api1/deposit/methods [get]
func (h *PaymentHandler) ListMethods(c *gin.Context) {
	// In production this would be fetched from DB/config.
	methods := []gin.H{
		{"code": "card_ru", "name": "Банковская карта РФ", "currency": "RUB"},
		{"code": "sbp",     "name": "СБП",                  "currency": "RUB"},
		{"code": "usdt_trc20", "name": "USDT TRC-20",       "currency": "USDT"},
		{"code": "card_intl", "name": "Visa/Mastercard",    "currency": "USD"},
	}
	c.JSON(http.StatusOK, methods)
}

// @Summary Create payment and get requisites
// @Tags deposit
// @Security ApiKeyAuth
// @Accept json
// @Produce json
// @Param body body createPaymentReq true "payment request"
// @Success 201 {object} paymentResponse
// @Router /api1/deposit/payments [post]
func (h *PaymentHandler) CreatePayment(c *gin.Context) {
	serviceID := middleware.ServiceID(c)
	var req createPaymentReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	req.Requisites.Bank = req.Bank
	req.Requisites.CardNumber = req.CardNumber
	req.Requisites.Wallet = req.Wallet
	req.Requisites.IBAN = req.IBAN

	p, err := h.paymentSvc.CreatePayment(c.Request.Context(),
		serviceID, req.ProviderID, req.AccountID, req.Currency, req.Amount, req.Requisites)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, gin.H{
		"payment_id":  p.ID,
		"external_id": p.ExternalID,
		"status":      p.Status,
		"requisites":  p.Requisites,
	})
}

// @Summary Get requisites for a payment
// @Tags deposit
// @Security ApiKeyAuth
// @Produce json
// @Param payment_id path string true "Payment ID"
// @Success 200 {object} service.Requisites
// @Router /api1/deposit/payments/{payment_id}/requisites [get]
func (h *PaymentHandler) GetRequisites(c *gin.Context) {
	req, err := h.paymentSvc.GetRequisites(c.Request.Context(), c.Param("payment_id"))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, req)
}

// @Summary Check / verify a payment
// @Tags deposit
// @Security ApiKeyAuth
// @Produce json
// @Param payment_id path string true "Payment ID"
// @Success 200 {object} model.Payment
// @Router /api1/deposit/payments/{payment_id}/check [post]
func (h *PaymentHandler) CheckPayment(c *gin.Context) {
	p, err := h.paymentSvc.CheckPayment(c.Request.Context(), c.Param("payment_id"))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, p)
}

// @Summary Get payment status
// @Tags deposit
// @Security ApiKeyAuth
// @Produce json
// @Param payment_id path string true "Payment ID"
// @Success 200 {object} map[string]string
// @Router /api1/deposit/payments/{payment_id}/status [get]
func (h *PaymentHandler) GetStatus(c *gin.Context) {
	status, err := h.paymentSvc.GetStatus(c.Request.Context(), c.Param("payment_id"))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"payment_id": c.Param("payment_id"), "status": status})
}

// @Summary List payments for this service
// @Tags deposit
// @Security ApiKeyAuth
// @Produce json
// @Param limit  query int false "limit"  default(50)
// @Param offset query int false "offset" default(0)
// @Success 200 {array} model.Payment
// @Router /api1/deposit/payments [get]
func (h *PaymentHandler) ListPayments(c *gin.Context) {
	serviceID := middleware.ServiceID(c)
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "50"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
	payments, err := h.paymentSvc.List(c.Request.Context(), serviceID, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, payments)
}

type createPaymentReq struct {
	ProviderID string  `json:"provider_id" binding:"required"`
	AccountID  string  `json:"account_id"  binding:"required"`
	Amount     float64 `json:"amount"      binding:"required,gt=0"`
	Currency   string  `json:"currency"    binding:"required,len=3"`
	// Requisites fields (optional depending on provider)
	CardNumber string `json:"card_number"`
	Bank       string `json:"bank"`
	Wallet     string `json:"wallet"`
	IBAN       string `json:"iban"`
	service.Requisites
}

type paymentResponse struct {
	PaymentID   string `json:"payment_id"`
	ExternalID  string `json:"external_id"`
	Status      string `json:"status"`
	Requisites  string `json:"requisites"`
}
