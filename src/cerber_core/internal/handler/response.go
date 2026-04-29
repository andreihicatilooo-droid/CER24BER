package handler

import (
	"encoding/json"
	"net/http"

	"github.com/cerber/billing/internal/crypto"
	"github.com/gin-gonic/gin"
)

// EncryptedJSON marshals data to JSON, encrypts it with AES-GCM-256 using the
// service's secret key, and returns { "data": "<Base64(Nonce||Ciphertext+Tag)>" }.
func EncryptedJSON(c *gin.Context, status int, data any, serviceKey []byte) {
	raw, err := json.Marshal(data)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "marshal error"})
		return
	}
	encrypted, err := crypto.Encrypt(serviceKey, raw)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "encryption error"})
		return
	}
	c.JSON(status, gin.H{"data": encrypted})
}
