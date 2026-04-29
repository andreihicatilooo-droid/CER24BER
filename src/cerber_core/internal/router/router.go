package router

import (
	"github.com/cerber/billing/internal/handler"
	"github.com/cerber/billing/internal/middleware"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

func Setup(
	r *gin.Engine,
	adminKey string,
	authSvc *service.AuthService,
	adminH *handler.AdminHandler,
	userH *handler.UserHandler,
	balanceH *handler.BalanceHandler,
	topupH *handler.TopupHandler,
) {
	apiKeyAuth := middleware.APIKeyAuth(authSvc)

	// ─── Admin (protected by static X-Admin-Key) ──────────────────────────────
	admin := r.Group("/admin", middleware.MustAdminKey(adminKey))
	{
		admin.POST("/services", adminH.CreateService)
	}

	// ─── API v1 (all require X-API-KEY) ──────────────────────────────────────
	v1 := r.Group("/api/v1", apiKeyAuth)
	{
		// POST /api/v1/user/add
		v1.POST("/user/add", userH.Add)

		// GET  /api/v1/balance?encrypted_user_hash=...
		v1.GET("/balance", balanceH.Get)

		// GET  /api/v1/topup/methods
		v1.GET("/topup/methods", topupH.ListMethods)

		// POST /api/v1/topup/create
		v1.POST("/topup/create", topupH.Create)

		// GET  /api/v1/topup/status?session_id=...
		v1.GET("/topup/status", topupH.Status)
	}
}

	// Swagger UI
	r.GET("/swagger/*any", ginSwagger.WrapHandler(swaggerFiles.Handler))

	api := r.Group("/api1")

	// ─── Auth (public) ────────────────────────────────────────────────
	auth := api.Group("/auth")
	{
		auth.POST("/register", authH.Register)
		auth.POST("/login", authH.Login)
		// Admin: create service credentials (requires JWT)
		auth.POST("/services", middleware.JWTAuth(jwtSecret), authH.CreateService)
	}

	// ─── Balance (API-key + JWT required) ─────────────────────────────
	balance := api.Group("/balance",
		middleware.APIKeyAuth(serviceRepo),
		middleware.JWTAuth(jwtSecret),
	)
	{
		balance.POST("/accounts", balanceH.CreateAccount)
		balance.GET("/accounts", balanceH.ListAccounts)
		balance.GET("/accounts/:account_id", balanceH.GetBalance)
		balance.POST("/accounts/:account_id/deposit", balanceH.Deposit)
		balance.POST("/accounts/:account_id/withdraw", balanceH.Withdraw)
		balance.GET("/accounts/:account_id/history", balanceH.History)
		balance.POST("/transfer", balanceH.Transfer)
		balance.GET("/total", balanceH.TotalBalance)
		balance.GET("/providers/:provider_id", balanceH.BalanceByProvider)
	}

	// ─── Deposit / Payments (API-key required) ─────────────────────────
	deposit := api.Group("/deposit", middleware.APIKeyAuth(serviceRepo))
	{
		deposit.GET("/methods", paymentH.ListMethods)
		deposit.POST("/payments", paymentH.CreatePayment)
		deposit.GET("/payments", paymentH.ListPayments)
		deposit.GET("/payments/:payment_id/requisites", paymentH.GetRequisites)
		deposit.POST("/payments/:payment_id/check", paymentH.CheckPayment)
		deposit.GET("/payments/:payment_id/status", paymentH.GetStatus)
	}
}
