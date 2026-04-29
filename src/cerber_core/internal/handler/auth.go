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
