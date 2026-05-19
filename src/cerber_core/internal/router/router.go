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

	// Admin (protected by static X-Admin-Key)
	admin := r.Group("/admin", middleware.MustAdminKey(adminKey))
	{
		admin.POST("/services", adminH.CreateService)
		admin.POST("/balance/adjust", adminH.AdjustBalance)
		admin.POST("/payments/:payment_id/confirm", adminH.ConfirmPayment)
		admin.POST("/payments/:payment_id/fail", adminH.FailPayment)
	}

	// API v1 (all require X-API-KEY)
	v1 := r.Group("/api/v1", apiKeyAuth)
	{
		v1.POST("/user/add", userH.Add)
		v1.GET("/balance", balanceH.Get)
		v1.GET("/balance/history", balanceH.History)
		v1.POST("/balance/adjust", balanceH.Adjust)
		v1.POST("/balance/hold", balanceH.Hold)
		v1.POST("/balance/unblock", balanceH.Unblock)
		v1.POST("/balance/transfer", balanceH.Transfer)

		v1.GET("/topup/methods", topupH.ListMethods)
		v1.POST("/topup/create", topupH.Create)
		v1.GET("/topup/status", topupH.Status)
		v1.POST("/topup/confirm", topupH.Confirm)

		v1.POST("/payment/create", topupH.CreatePayment)
		v1.GET("/payment/status", topupH.PaymentStatus)
		v1.POST("/payment/webhook", topupH.Webhook)
		v1.POST("/payment/refund", topupH.Refund)

		v1.POST("/withdrawal/create", balanceH.CreateWithdrawal)
		v1.POST("/withdrawal/cancel", balanceH.CancelWithdrawal)
	}
}
