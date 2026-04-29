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
