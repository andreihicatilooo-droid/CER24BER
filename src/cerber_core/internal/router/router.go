package router

import (
	"github.com/cerber/billing/internal/handler"
	"github.com/cerber/billing/internal/middleware"
	"github.com/cerber/billing/internal/repository"
	"github.com/gin-gonic/gin"
	swaggerFiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"
)

func Setup(
	r *gin.Engine,
	jwtSecret string,
	serviceRepo *repository.ServiceRepo,
	authH *handler.AuthHandler,
	balanceH *handler.BalanceHandler,
	paymentH *handler.PaymentHandler,
) {
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
