package middleware

import (
	"net/http"

	"github.com/cerber/billing/internal/model"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

const ctxServiceKey = "svc"

// APIKeyAuth validates X-API-KEY header, loads the service record,
// decrypts its secret key and injects *model.Service into the context.
func APIKeyAuth(authSvc *service.AuthService) gin.HandlerFunc {
	return func(c *gin.Context) {
		rawKey := c.GetHeader("X-API-KEY")
		if rawKey == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "missing X-API-KEY header"})
			return
		}
		svc, err := authSvc.ValidateAPIKey(c.Request.Context(), rawKey)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "invalid API key"})
			return
		}
		c.Set(ctxServiceKey, svc)
		c.Next()
	}
}

// MustAdminKey is a simple static-key guard for admin endpoints.
func MustAdminKey(adminKey string) gin.HandlerFunc {
	return func(c *gin.Context) {
		if c.GetHeader("X-Admin-Key") != adminKey {
			c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "forbidden"})
			return
		}
		c.Next()
	}
}

// GetService retrieves the authenticated *model.Service from the Gin context.
func GetService(c *gin.Context) *model.Service {
	v, _ := c.Get(ctxServiceKey)
	svc, _ := v.(*model.Service)
	return svc
}

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
