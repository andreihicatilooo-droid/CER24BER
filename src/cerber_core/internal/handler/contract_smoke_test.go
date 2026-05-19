package handler

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/cerber/billing/internal/model"
	"github.com/gin-gonic/gin"
)

func TestTopupHandlerPaymentStatusRequiresPaymentID(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := NewTopupHandler(nil)

	rec := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(rec)
	c.Request = httptest.NewRequest(http.MethodGet, "/api/v1/payment/status", nil)
	c.Set("svc", &model.Service{ID: "svc", SecretKey: bytes.Repeat([]byte{1}, 32)})

	h.PaymentStatus(c)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected %d, got %d", http.StatusBadRequest, rec.Code)
	}
}

func TestBalanceHandlerTransferValidatesBody(t *testing.T) {
	gin.SetMode(gin.TestMode)
	h := NewBalanceHandler(nil)

	rec := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(rec)
	c.Request = httptest.NewRequest(http.MethodPost, "/api/v1/balance/transfer", bytes.NewBufferString(`{}`))
	c.Request.Header.Set("Content-Type", "application/json")
	c.Set("svc", &model.Service{ID: "svc", SecretKey: bytes.Repeat([]byte{2}, 32)})

	h.Transfer(c)

	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected %d, got %d", http.StatusBadRequest, rec.Code)
	}
}
