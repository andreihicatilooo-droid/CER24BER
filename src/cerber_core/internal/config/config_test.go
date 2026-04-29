package config

import (
	"encoding/hex"
	"os"
	"testing"
)

func TestLoad_Success(t *testing.T) {
	// Setup test environment variables
	testAESKey := make([]byte, 32)
	testHMACKey := make([]byte, 32)
	for i := range testAESKey {
		testAESKey[i] = byte(i)
		testHMACKey[i] = byte(32 + i)
	}

	os.Setenv("MASTER_AES_KEY", hex.EncodeToString(testAESKey))
	os.Setenv("MASTER_HMAC_KEY", hex.EncodeToString(testHMACKey))
	os.Setenv("ADMIN_KEY", "test-admin-key")
	defer func() {
		os.Unsetenv("MASTER_AES_KEY")
		os.Unsetenv("MASTER_HMAC_KEY")
		os.Unsetenv("ADMIN_KEY")
		os.Unsetenv("AES_SECRET_KEY")
		os.Unsetenv("BILLING_DATABASE_URL")
		os.Unsetenv("USERS_DATABASE_URL")
	}()

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() failed: %v", err)
	}

	if cfg.AdminKey != "test-admin-key" {
		t.Errorf("AdminKey = %q, want %q", cfg.AdminKey, "test-admin-key")
	}
	if len(cfg.MasterAESKey) != 32 {
		t.Errorf("MasterAESKey length = %d, want 32", len(cfg.MasterAESKey))
	}
	if len(cfg.MasterHMACKey) != 32 {
		t.Errorf("MasterHMACKey length = %d, want 32", len(cfg.MasterHMACKey))
	}
	if len(cfg.AESSecretKey) != 32 {
		t.Errorf("AESSecretKey length = %d, want 32", len(cfg.AESSecretKey))
	}

	// By default, AESSecretKey should equal MasterAESKey
	for i := range cfg.MasterAESKey {
		if cfg.AESSecretKey[i] != cfg.MasterAESKey[i] {
			t.Errorf("AESSecretKey[%d] = %d, want %d (should default to MasterAESKey)", i, cfg.AESSecretKey[i], cfg.MasterAESKey[i])
			break
		}
	}

	// Check fallback values for database URLs
	expectedBillingURL := "postgres://billing:billing@localhost:5432/billing?sslmode=disable"
	if cfg.BillingDatabaseURL != expectedBillingURL {
		t.Errorf("BillingDatabaseURL = %q, want %q", cfg.BillingDatabaseURL, expectedBillingURL)
	}

	expectedUsersURL := "postgres://usersvc:usersvc@localhost:5432/users?sslmode=disable"
	if cfg.UsersDatabaseURL != expectedUsersURL {
		t.Errorf("UsersDatabaseURL = %q, want %q", cfg.UsersDatabaseURL, expectedUsersURL)
	}
}

func TestLoad_CustomAESSecretKey(t *testing.T) {
	testAESKey := make([]byte, 32)
	testHMACKey := make([]byte, 32)
	customAESSecret := make([]byte, 32)
	for i := range testAESKey {
		testAESKey[i] = byte(i)
		testHMACKey[i] = byte(32 + i)
		customAESSecret[i] = byte(64 + i)
	}

	os.Setenv("MASTER_AES_KEY", hex.EncodeToString(testAESKey))
	os.Setenv("MASTER_HMAC_KEY", hex.EncodeToString(testHMACKey))
	os.Setenv("AES_SECRET_KEY", hex.EncodeToString(customAESSecret))
	os.Setenv("ADMIN_KEY", "test-admin-key")
	defer func() {
		os.Unsetenv("MASTER_AES_KEY")
		os.Unsetenv("MASTER_HMAC_KEY")
		os.Unsetenv("AES_SECRET_KEY")
		os.Unsetenv("ADMIN_KEY")
	}()

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() failed: %v", err)
	}

	// AESSecretKey should be different from MasterAESKey when explicitly set
	for i := range cfg.MasterAESKey {
		if cfg.AESSecretKey[i] == cfg.MasterAESKey[i] {
			t.Errorf("AESSecretKey should differ from MasterAESKey when explicitly set")
			break
		}
	}

	// Verify it matches the custom value
	for i := range customAESSecret {
		if cfg.AESSecretKey[i] != customAESSecret[i] {
			t.Errorf("AESSecretKey[%d] = %d, want %d", i, cfg.AESSecretKey[i], customAESSecret[i])
			break
		}
	}
}

func TestLoad_MissingMASTER_AES_KEY(t *testing.T) {
	os.Unsetenv("MASTER_AES_KEY")
	os.Setenv("MASTER_HMAC_KEY", hex.EncodeToString(make([]byte, 32)))
	os.Setenv("ADMIN_KEY", "test")
	defer func() {
		os.Unsetenv("MASTER_HMAC_KEY")
		os.Unsetenv("ADMIN_KEY")
	}()

	_, err := Load()
	if err == nil {
		t.Error("Load() should fail when MASTER_AES_KEY is missing")
	}
}

func TestLoad_InvalidMASTER_AES_KEY(t *testing.T) {
	os.Setenv("MASTER_AES_KEY", "not-hex")
	os.Setenv("MASTER_HMAC_KEY", hex.EncodeToString(make([]byte, 32)))
	os.Setenv("ADMIN_KEY", "test")
	defer func() {
		os.Unsetenv("MASTER_AES_KEY")
		os.Unsetenv("MASTER_HMAC_KEY")
		os.Unsetenv("ADMIN_KEY")
	}()

	_, err := Load()
	if err == nil {
		t.Error("Load() should fail when MASTER_AES_KEY is invalid hex")
	}
}

func TestLoad_WrongLengthMASTER_AES_KEY(t *testing.T) {
	shortKey := make([]byte, 16) // Only 16 bytes, not 32
	os.Setenv("MASTER_AES_KEY", hex.EncodeToString(shortKey))
	os.Setenv("MASTER_HMAC_KEY", hex.EncodeToString(make([]byte, 32)))
	os.Setenv("ADMIN_KEY", "test")
	defer func() {
		os.Unsetenv("MASTER_AES_KEY")
		os.Unsetenv("MASTER_HMAC_KEY")
		os.Unsetenv("ADMIN_KEY")
	}()

	_, err := Load()
	if err == nil {
		t.Error("Load() should fail when MASTER_AES_KEY is not 32 bytes")
	}
}

func TestLoad_MissingADMIN_KEY(t *testing.T) {
	os.Setenv("MASTER_AES_KEY", hex.EncodeToString(make([]byte, 32)))
	os.Setenv("MASTER_HMAC_KEY", hex.EncodeToString(make([]byte, 32)))
	os.Unsetenv("ADMIN_KEY")
	defer func() {
		os.Unsetenv("MASTER_AES_KEY")
		os.Unsetenv("MASTER_HMAC_KEY")
	}()

	_, err := Load()
	if err == nil {
		t.Error("Load() should fail when ADMIN_KEY is missing")
	}
}

func TestLoad_CustomDatabaseURLs(t *testing.T) {
	testAESKey := make([]byte, 32)
	testHMACKey := make([]byte, 32)
	
	os.Setenv("MASTER_AES_KEY", hex.EncodeToString(testAESKey))
	os.Setenv("MASTER_HMAC_KEY", hex.EncodeToString(testHMACKey))
	os.Setenv("ADMIN_KEY", "test")
	os.Setenv("BILLING_DATABASE_URL", "postgres://custom:pass@billing:5432/billing")
	os.Setenv("USERS_DATABASE_URL", "postgres://custom:pass@users:5432/users")
	defer func() {
		os.Unsetenv("MASTER_AES_KEY")
		os.Unsetenv("MASTER_HMAC_KEY")
		os.Unsetenv("ADMIN_KEY")
		os.Unsetenv("BILLING_DATABASE_URL")
		os.Unsetenv("USERS_DATABASE_URL")
	}()

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load() failed: %v", err)
	}

	if cfg.BillingDatabaseURL != "postgres://custom:pass@billing:5432/billing" {
		t.Errorf("BillingDatabaseURL = %q, want custom URL", cfg.BillingDatabaseURL)
	}
	if cfg.UsersDatabaseURL != "postgres://custom:pass@users:5432/users" {
		t.Errorf("UsersDatabaseURL = %q, want custom URL", cfg.UsersDatabaseURL)
	}
}
