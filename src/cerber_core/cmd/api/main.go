// @title           Cerber Billing API
// @version         1.0
// @description     Multi-service billing system with balance management and payment processing.
// @host            localhost:8080
// @BasePath        /
// @securityDefinitions.apikey ApiKeyAuth
// @in header
// @name X-API-Key
// @securityDefinitions.apikey BearerAuth
// @in header
// @name Authorization
package main

import (
	"log"

	_ "github.com/cerber/billing/docs"
	"github.com/cerber/billing/internal/config"
	"github.com/cerber/billing/internal/db"
	"github.com/cerber/billing/internal/handler"
	"github.com/cerber/billing/internal/repository"
	"github.com/cerber/billing/internal/router"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

func main() {
	cfg := config.Load()

	database, err := db.Connect(cfg.DatabaseURL)
	if err != nil {
		log.Fatalf("db connect: %v", err)
	}
	defer database.Close()

	// Repositories
	userRepo    := repository.NewUserRepo(database)
	serviceRepo := repository.NewServiceRepo(database)
	accountRepo := repository.NewAccountRepo(database)
	txRepo      := repository.NewTransactionRepo(database)
	paymentRepo := repository.NewPaymentRepo(database)

	// Services
	authSvc    := service.NewAuthService(userRepo, serviceRepo, cfg.JWTSecret)
	balanceSvc := service.NewBalanceService(database.DB, accountRepo, txRepo)
	paymentSvc := service.NewPaymentService(paymentRepo, balanceSvc)

	// Handlers
	authH    := handler.NewAuthHandler(authSvc)
	balanceH := handler.NewBalanceHandler(balanceSvc)
	paymentH := handler.NewPaymentHandler(paymentSvc)

	r := gin.Default()
	router.Setup(r, cfg.JWTSecret, serviceRepo, authH, balanceH, paymentH)

	log.Printf("Billing API listening on :%s", cfg.ServerPort)
	if err := r.Run(":" + cfg.ServerPort); err != nil {
		log.Fatalf("server: %v", err)
	}
}
