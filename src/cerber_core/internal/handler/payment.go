package handler

import (
	"net/http"

	"github.com/cerber/billing/internal/middleware"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

type TopupHandler struct {
	topupSvc *service.TopupService
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
	var req struct {
		EncryptedUserHash string  `json:"encrypted_user_hash" binding:"required"`
		MethodID          string  `json:"method_id"           binding:"required"`
		AmountUSDT        float64 `json:"amount_usdt"         binding:"required,gt=0"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	userHash, err := service.DecryptUserHash(req.EncryptedUserHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	session, err := h.topupSvc.CreateSession(c.Request.Context(), svc.ID, userHash, req.MethodID, req.AmountUSDT)
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
		EncryptedJSON(c, http.StatusNotFound, gin.H{"error": err.Error()}, svc.SecretKey)
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
