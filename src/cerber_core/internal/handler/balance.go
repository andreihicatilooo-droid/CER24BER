package handler

import (
	"net/http"

	"github.com/cerber/billing/internal/middleware"
	"github.com/cerber/billing/internal/service"
	"github.com/gin-gonic/gin"
)

type BalanceHandler struct {
	balanceSvc *service.BalanceService
}

func NewBalanceHandler(balanceSvc *service.BalanceService) *BalanceHandler {
	return &BalanceHandler{balanceSvc: balanceSvc}
}

// Get returns the user's USDT balance and its RUB equivalent.
// Query param: encrypted_user_hash=<Base64 AES-GCM>
func (h *BalanceHandler) Get(c *gin.Context) {
	svc := middleware.GetService(c)
	encHash := c.Query("encrypted_user_hash")
	userHash, err := service.DecryptUserHash(encHash, svc.SecretKey)
	if err != nil {
		EncryptedJSON(c, http.StatusBadRequest, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	result, err := h.balanceSvc.GetBalance(c.Request.Context(), svc.ID, userHash)
	if err != nil {
		EncryptedJSON(c, http.StatusInternalServerError, gin.H{"error": err.Error()}, svc.SecretKey)
		return
	}
	EncryptedJSON(c, http.StatusOK, result, svc.SecretKey)
}

// @Summary Create account
// @Tags balance
// @Security ApiKeyAuth
// @Security BearerAuth
// @Accept json
// @Produce json
// @Param body body createAccountReq true "account"
// @Success 201 {object} model.Account
// @Router /api1/balance/accounts [post]
func (h *BalanceHandler) CreateAccount(c *gin.Context) {
	userID := middleware.UserID(c)
	var req createAccountReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	a, err := h.balanceSvc.CreateAccount(c.Request.Context(), userID, req.Name, req.Currency)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusCreated, a)
}

// @Summary Get balance for an account
// @Tags balance
// @Security ApiKeyAuth
// @Produce json
// @Param account_id path string true "Account ID"
// @Success 200 {object} model.Account
// @Router /api1/balance/accounts/{account_id} [get]
func (h *BalanceHandler) GetBalance(c *gin.Context) {
	a, err := h.balanceSvc.GetBalance(c.Request.Context(), c.Param("account_id"))
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, a)
}

// @Summary List all accounts for the current user
// @Tags balance
// @Security BearerAuth
// @Produce json
// @Success 200 {array} model.Account
// @Router /api1/balance/accounts [get]
func (h *BalanceHandler) ListAccounts(c *gin.Context) {
	userID := middleware.UserID(c)
	accounts, err := h.balanceSvc.GetBalancesByUser(c.Request.Context(), userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, accounts)
}

// @Summary Get total balance across all accounts (by currency)
// @Tags balance
// @Security ApiKeyAuth
// @Produce json
// @Param currency query string true "Currency code (e.g. USD)"
// @Success 200 {object} map[string]float64
// @Router /api1/balance/total [get]
func (h *BalanceHandler) TotalBalance(c *gin.Context) {
	currency := c.Query("currency")
	if currency == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "currency required"})
		return
	}
	total, err := h.balanceSvc.GetTotalBalance(c.Request.Context(), currency)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"currency": currency, "total": total})
}

// @Summary Get balances by provider
// @Tags balance
// @Security ApiKeyAuth
// @Produce json
// @Param provider_id path string true "Provider ID"
// @Success 200 {array} model.Account
// @Router /api1/balance/providers/{provider_id} [get]
func (h *BalanceHandler) BalanceByProvider(c *gin.Context) {
	accounts, err := h.balanceSvc.GetBalanceByProvider(c.Request.Context(), c.Param("provider_id"))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, accounts)
}

// @Summary Deposit to account
// @Tags balance
// @Security ApiKeyAuth
// @Accept json
// @Produce json
// @Param account_id path string true "Account ID"
// @Param body body amountReq true "amount"
// @Success 200 {object} model.Transaction
// @Router /api1/balance/accounts/{account_id}/deposit [post]
func (h *BalanceHandler) Deposit(c *gin.Context) {
	var req amountReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	t, err := h.balanceSvc.Deposit(c.Request.Context(), c.Param("account_id"), req.Amount, req.Description)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, t)
}

// @Summary Withdraw from account
// @Tags balance
// @Security ApiKeyAuth
// @Accept json
// @Produce json
// @Param account_id path string true "Account ID"
// @Param body body amountReq true "amount"
// @Success 200 {object} model.Transaction
// @Router /api1/balance/accounts/{account_id}/withdraw [post]
func (h *BalanceHandler) Withdraw(c *gin.Context) {
	var req amountReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	t, err := h.balanceSvc.Withdraw(c.Request.Context(), c.Param("account_id"), req.Amount, req.Description)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, t)
}

// @Summary Transfer between accounts
// @Tags balance
// @Security ApiKeyAuth
// @Accept json
// @Produce json
// @Param body body transferReq true "transfer"
// @Success 200 {object} model.Transaction
// @Router /api1/balance/transfer [post]
func (h *BalanceHandler) Transfer(c *gin.Context) {
	var req transferReq
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	t, err := h.balanceSvc.Transfer(c.Request.Context(), req.FromAccountID, req.ToAccountID, req.Amount, req.Description)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, t)
}

// @Summary Transaction history for an account
// @Tags balance
// @Security ApiKeyAuth
// @Produce json
// @Param account_id path string true "Account ID"
// @Param limit  query int false "limit"  default(50)
// @Param offset query int false "offset" default(0)
// @Success 200 {array} model.Transaction
// @Router /api1/balance/accounts/{account_id}/history [get]
func (h *BalanceHandler) History(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "50"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
	txs, err := h.balanceSvc.History(c.Request.Context(), c.Param("account_id"), limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, txs)
}

// DTO types
type createAccountReq struct {
	Name     string `json:"name"     binding:"required"`
	Currency string `json:"currency" binding:"required,len=3"`
}

type amountReq struct {
	Amount      float64 `json:"amount"      binding:"required,gt=0"`
	Description string  `json:"description"`
}

type transferReq struct {
	FromAccountID string  `json:"from_account_id" binding:"required"`
	ToAccountID   string  `json:"to_account_id"   binding:"required"`
	Amount        float64 `json:"amount"          binding:"required,gt=0"`
	Description   string  `json:"description"`
}
