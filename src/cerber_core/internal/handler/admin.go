package handler

import (
	"net/http"

	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

// AdminHandler handles privileged operations (service creation).
type AdminHandler struct {
	authSvc *service.AuthService
}

func NewAdminHandler(authSvc *service.AuthService) *AdminHandler {
	return &AdminHandler{authSvc: authSvc}
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
