package middleware

import "github.com/cerber/billing/internal/service"

// parseJWT delegates to the service package to avoid circular imports.
func parseJWT(tokenStr, secret string) (*service.Claims, error) {
	return service.ParseJWT(tokenStr, secret)
}
