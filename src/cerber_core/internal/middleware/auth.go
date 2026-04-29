package middleware

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net/http"
	"strings"

	"github.com/cerber/billing/internal/repository"
	"github.com/gin-gonic/gin"
	"golang.org/x/crypto/bcrypt"
)

const (
	ctxServiceKey = "service_id"
)

// APIKeyAuth validates X-API-Key and X-API-Secret headers against the services table.
func APIKeyAuth(serviceRepo *repository.ServiceRepo) gin.HandlerFunc {
	return func(c *gin.Context) {
		apiKey := c.GetHeader("X-API-Key")
		apiSecret := c.GetHeader("X-API-Secret")
		if apiKey == "" || apiSecret == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing API credentials"})
			return
		}

		svc, err := serviceRepo.FindByAPIKey(c.Request.Context(), apiKey)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid API key"})
			return
		}

		if err := bcrypt.CompareHashAndPassword([]byte(svc.APISecret), []byte(apiSecret)); err != nil {
			// Fallback: compare as HMAC-SHA256 signed key for service-to-service use
			mac := hmac.New(sha256.New, []byte(svc.APIKey))
			mac.Write([]byte(apiSecret))
			expected := hex.EncodeToString(mac.Sum(nil))
			if !hmac.Equal([]byte(expected), []byte(apiSecret)) {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid API secret"})
				return
			}
		}

		c.Set(ctxServiceKey, svc.ID)
		c.Next()
	}
}

// ServiceID retrieves the authenticated service ID from the context.
func ServiceID(c *gin.Context) string {
	v, _ := c.Get(ctxServiceKey)
	s, _ := v.(string)
	return s
}

// JWTAuth validates Bearer JWT token.
func JWTAuth(jwtSecret string) gin.HandlerFunc {
	return func(c *gin.Context) {
		header := c.GetHeader("Authorization")
		if !strings.HasPrefix(header, "Bearer ") {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing bearer token"})
			return
		}
		tokenStr := strings.TrimPrefix(header, "Bearer ")

		claims, err := parseJWT(tokenStr, jwtSecret)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid token"})
			return
		}
		c.Set("user_id", claims.UserID)
		c.Next()
	}
}

// UserID retrieves the authenticated user ID from the context.
func UserID(c *gin.Context) string {
	v, _ := c.Get("user_id")
	s, _ := v.(string)
	return s
}
