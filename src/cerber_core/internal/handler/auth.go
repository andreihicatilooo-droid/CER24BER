package handler

import (
	"net/http"

	"github.com/cerber/billing/internal/middleware"
	"github.com/cerber/billing/internal/repository"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

// UserHandler handles user initialization in the billing registry.
type UserHandler struct {
	userRepo *repository.UserRepo
}

func NewUserHandler(userRepo *repository.UserRepo) *UserHandler {
	return &UserHandler{userRepo: userRepo}
}

// Add initialises a billing record for a new user.
// Body: { "encrypted_user_hash": "<Base64 AES-GCM ciphertext>" }
func (h *UserHandler) Add(c *gin.Context) {
	svc := middleware.GetService(c)
	var req struct {
		EncryptedUserHash string `json:"encrypted_user_hash" binding:"required"`
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
	user, err := h.userRepo.Upsert(c.Request.Context(), userHash)
	if err != nil {
		EncryptedJSON(c, http.StatusInternalServerError, gin.H{"error": "internal error"}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, gin.H{
		"user_hash":  user.UserHash,
		"status":     user.Status,
		"created_at": user.CreatedAt,
	}, svc.SecretKey)
}

// @Summary Register new user
// @Tags auth
// @Accept json
// @Produce json
// @Param body body registerRequest true "credentials"
// @Success 201 {object} map[string]string
// @Router /api1/auth/register [post]
func (h *AuthHandler) Register(c *gin.Context) {
	var req registerRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	u, err := h.authSvc.RegisterUser(c.Request.Context(), req.Email, req.Password)
	if err != nil {
		c.JSON(http.StatusConflict, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, gin.H{"id": u.ID, "email": u.Email})
}

// @Summary Login
// @Tags auth
// @Accept json
// @Produce json
// @Param body body registerRequest true "credentials"
// @Success 200 {object} map[string]string
// @Router /api1/auth/login [post]
func (h *AuthHandler) Login(c *gin.Context) {
	var req registerRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	token, err := h.authSvc.LoginUser(c.Request.Context(), req.Email, req.Password)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"token": token})
}

// @Summary Create service (admin)
// @Tags auth
// @Security BearerAuth
// @Accept json
// @Produce json
// @Param body body createServiceRequest true "service name"
// @Success 201 {object} map[string]string
// @Router /api1/auth/services [post]
func (h *AuthHandler) CreateService(c *gin.Context) {
	_ = middleware.UserID(c) // must be authenticated
	var req createServiceRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	svc, rawSecret, err := h.authSvc.CreateService(c.Request.Context(), req.Name)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	// Return raw secret only once — it is hashed in the DB.
	c.JSON(http.StatusCreated, gin.H{
		"id":         svc.ID,
		"name":       svc.Name,
		"api_key":    svc.APIKey,
		"api_secret": rawSecret,
	})
}

type registerRequest struct {
	Email    string `json:"email"    binding:"required,email"`
	Password string `json:"password" binding:"required,min=8"`
}

type createServiceRequest struct {
	Name string `json:"name" binding:"required"`
}
