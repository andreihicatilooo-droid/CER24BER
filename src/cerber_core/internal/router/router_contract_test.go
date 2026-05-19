package router

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"
)

type routeCase struct {
	name           string
	method         string
	path           string
	body           []byte
	expectedStatus int
}

func TestAPIRoutesRequireAPIKey(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	Setup(r, "admin-secret", nil, nil, nil, nil, nil)

	cases := []routeCase{
		{name: "balance", method: http.MethodGet, path: "/api/v1/balance", expectedStatus: http.StatusUnauthorized},
		{name: "balance-history", method: http.MethodGet, path: "/api/v1/balance/history", expectedStatus: http.StatusUnauthorized},
		{name: "balance-adjust", method: http.MethodPost, path: "/api/v1/balance/adjust", body: []byte(`{}`), expectedStatus: http.StatusUnauthorized},
		{name: "balance-hold", method: http.MethodPost, path: "/api/v1/balance/hold", body: []byte(`{}`), expectedStatus: http.StatusUnauthorized},
		{name: "balance-unblock", method: http.MethodPost, path: "/api/v1/balance/unblock", body: []byte(`{}`), expectedStatus: http.StatusUnauthorized},
		{name: "balance-transfer", method: http.MethodPost, path: "/api/v1/balance/transfer", body: []byte(`{}`), expectedStatus: http.StatusUnauthorized},
		{name: "withdrawal-create", method: http.MethodPost, path: "/api/v1/withdrawal/create", body: []byte(`{}`), expectedStatus: http.StatusUnauthorized},
		{name: "withdrawal-cancel", method: http.MethodPost, path: "/api/v1/withdrawal/cancel", body: []byte(`{}`), expectedStatus: http.StatusUnauthorized},
		{name: "payment-create", method: http.MethodPost, path: "/api/v1/payment/create", body: []byte(`{}`), expectedStatus: http.StatusUnauthorized},
		{name: "payment-status", method: http.MethodGet, path: "/api/v1/payment/status", expectedStatus: http.StatusUnauthorized},
		{name: "payment-webhook", method: http.MethodPost, path: "/api/v1/payment/webhook", body: []byte(`{}`), expectedStatus: http.StatusUnauthorized},
		{name: "payment-refund", method: http.MethodPost, path: "/api/v1/payment/refund", body: []byte(`{}`), expectedStatus: http.StatusUnauthorized},
		{name: "topup-create-legacy", method: http.MethodPost, path: "/api/v1/topup/create", body: []byte(`{}`), expectedStatus: http.StatusUnauthorized},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(tc.method, tc.path, bytes.NewReader(tc.body))
			if tc.body != nil {
				req.Header.Set("Content-Type", "application/json")
			}
			rec := httptest.NewRecorder()
			r.ServeHTTP(rec, req)
			if rec.Code != tc.expectedStatus {
				t.Fatalf("expected %d, got %d", tc.expectedStatus, rec.Code)
			}
		})
	}
}

func TestAdminRoutesRequireAdminKey(t *testing.T) {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	Setup(r, "admin-secret", nil, nil, nil, nil, nil)

	cases := []routeCase{
		{name: "admin-create-service", method: http.MethodPost, path: "/admin/services", body: []byte(`{"name":"svc"}`), expectedStatus: http.StatusForbidden},
		{name: "admin-adjust-balance", method: http.MethodPost, path: "/admin/balance/adjust", body: []byte(`{}`), expectedStatus: http.StatusForbidden},
		{name: "admin-confirm-payment", method: http.MethodPost, path: "/admin/payments/123/confirm", body: []byte(`{}`), expectedStatus: http.StatusForbidden},
		{name: "admin-fail-payment", method: http.MethodPost, path: "/admin/payments/123/fail", body: []byte(`{}`), expectedStatus: http.StatusForbidden},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			req := httptest.NewRequest(tc.method, tc.path, bytes.NewReader(tc.body))
			req.Header.Set("Content-Type", "application/json")
			rec := httptest.NewRecorder()
			r.ServeHTTP(rec, req)
			if rec.Code != tc.expectedStatus {
				t.Fatalf("expected %d, got %d", tc.expectedStatus, rec.Code)
			}
		})
	}
}
