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

	billingDB, err := db.Connect(cfg.BillingDatabaseURL)
	if err != nil {
		log.Fatalf("billing-db connect: %v", err)
	}
	defer billingDB.Close()

	// usersDB holds PII (email, password_hash). The billing API never queries it
	// directly — it is established here so the connection is validated at startup
	// and can be passed to a future auth service without refactoring main.
	usersDB, err := db.Connect(cfg.UsersDatabaseURL)
	if err != nil {
		log.Fatalf("users-db connect: %v", err)
	}
	defer usersDB.Close()
	_ = usersDB // reserved for future PII auth service

	// ─── Repositories ─────────────────────────────────────────────────────────
	// billing-db: services, users (user_hash registry), balances, topup, exchange
	// users-db:   PII (email, password_hash) — not used by billing API
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
