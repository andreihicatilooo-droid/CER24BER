package main

import (
	"log"

	"github.com/cerber/billing/internal/config"
	"github.com/cerber/billing/internal/db"
	"github.com/cerber/billing/internal/handler"
	"github.com/cerber/billing/internal/repository"
	"github.com/cerber/billing/internal/router"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("config: %v", err)
	}

	billingDB, err := db.Connect(cfg.BillingDSN)
	if err != nil {
		log.Fatalf("billing-db connect: %v", err)
	}
	defer billingDB.Close()

	// ─── Repositories ─────────────────────────────────────────────────────────
	serviceRepo  := repository.NewServiceRepo(billingDB)
	userRepo     := repository.NewUserRepo(billingDB)
	balanceRepo  := repository.NewBalanceRepo(billingDB)
	txRepo       := repository.NewTransactionRepo(billingDB)
	topupRepo    := repository.NewTopupRepo(billingDB)
	exchangeRepo := repository.NewExchangeRepo(billingDB)

	// ─── Services ─────────────────────────────────────────────────────────────
	authSvc    := service.NewAuthService(serviceRepo, cfg.MasterAESKey, cfg.MasterHMACKey)
	balanceSvc := service.NewBalanceService(balanceRepo, txRepo, exchangeRepo)
	topupSvc   := service.NewTopupService(topupRepo, balanceSvc, exchangeRepo)

	// ─── Handlers ─────────────────────────────────────────────────────────────
	adminH   := handler.NewAdminHandler(authSvc)
	userH    := handler.NewUserHandler(userRepo)
	balanceH := handler.NewBalanceHandler(balanceSvc)
	topupH   := handler.NewTopupHandler(topupSvc)

	r := gin.Default()
	router.Setup(r, cfg.AdminKey, authSvc, adminH, userH, balanceH, topupH)

	log.Printf("CERBER CORE listening on :%s", cfg.ServerPort)
	if err := r.Run(":" + cfg.ServerPort); err != nil {
		log.Fatalf("server: %v", err)
	}
}


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
