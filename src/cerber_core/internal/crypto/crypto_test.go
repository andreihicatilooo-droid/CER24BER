package crypto_test

import (
	"bytes"
	"encoding/base64"
	"strings"
	"testing"

	"github.com/cerber/billing/internal/crypto"
)

// ─── Encrypt / Decrypt ───────────────────────────────────────────────────────

func TestEncryptDecryptRoundtrip(t *testing.T) {
	key := make([]byte, 32)
	for i := range key {
		key[i] = byte(i)
	}
	plaintext := []byte("hello cerber billing")

	encoded, err := crypto.Encrypt(key, plaintext)
	if err != nil {
		t.Fatalf("Encrypt: %v", err)
	}
	if encoded == "" {
		t.Fatal("Encrypt returned empty string")
	}

	got, err := crypto.Decrypt(key, encoded)
	if err != nil {
		t.Fatalf("Decrypt: %v", err)
	}
	if !bytes.Equal(got, plaintext) {
		t.Fatalf("roundtrip mismatch: got %q want %q", got, plaintext)
	}
}

func TestEncryptProducesUniqueNonces(t *testing.T) {
	key := make([]byte, 32)
	plaintext := []byte("same plaintext")

	a, _ := crypto.Encrypt(key, plaintext)
	b, _ := crypto.Encrypt(key, plaintext)

	if a == b {
		t.Error("Encrypt should produce different ciphertexts on every call (random nonce)")
	}
}

func TestDecryptWrongKeyFails(t *testing.T) {
	key := make([]byte, 32)
	wrongKey := make([]byte, 32)
	wrongKey[0] = 0xFF

	encoded, _ := crypto.Encrypt(key, []byte("secret"))

	_, err := crypto.Decrypt(wrongKey, encoded)
	if err == nil {
		t.Fatal("Decrypt with wrong key should fail")
	}
}

func TestDecryptTamperedCiphertextFails(t *testing.T) {
	key := make([]byte, 32)
	encoded, _ := crypto.Encrypt(key, []byte("secret data"))

	raw, _ := base64.StdEncoding.DecodeString(encoded)
	// Flip a bit in the ciphertext body (past the 12-byte nonce)
	raw[13] ^= 0x01
	tampered := base64.StdEncoding.EncodeToString(raw)

	_, err := crypto.Decrypt(key, tampered)
	if err == nil {
		t.Fatal("Decrypt with tampered ciphertext should fail (GCM auth tag mismatch)")
	}
}

func TestEncryptKeyTooShortFails(t *testing.T) {
	_, err := crypto.Encrypt(make([]byte, 16), []byte("test"))
	if err == nil {
		t.Fatal("Encrypt with 16-byte key should return error")
	}
}

func TestDecryptKeyTooShortFails(t *testing.T) {
	key := make([]byte, 32)
	encoded, _ := crypto.Encrypt(key, []byte("test"))

	_, err := crypto.Decrypt(make([]byte, 16), encoded)
	if err == nil {
		t.Fatal("Decrypt with 16-byte key should return error")
	}
}

func TestDecryptInvalidBase64Fails(t *testing.T) {
	key := make([]byte, 32)
	_, err := crypto.Decrypt(key, "not-valid-base64!!!")
	if err == nil {
		t.Fatal("Decrypt with invalid base64 should fail")
	}
}

func TestDecryptTooShortFails(t *testing.T) {
	key := make([]byte, 32)
	// 4 bytes — shorter than nonce (12 bytes)
	short := base64.StdEncoding.EncodeToString([]byte{0x01, 0x02, 0x03, 0x04})
	_, err := crypto.Decrypt(key, short)
	if err == nil {
		t.Fatal("Decrypt with ciphertext shorter than nonce should fail")
	}
}

func TestEncryptEmptyPlaintext(t *testing.T) {
	key := make([]byte, 32)
	encoded, err := crypto.Encrypt(key, []byte{})
	if err != nil {
		t.Fatalf("Encrypt empty plaintext: %v", err)
	}
	got, err := crypto.Decrypt(key, encoded)
	if err != nil {
		t.Fatalf("Decrypt empty plaintext: %v", err)
	}
	if len(got) != 0 {
		t.Fatalf("expected empty plaintext, got %q", got)
	}
}

// ─── HMACHash ────────────────────────────────────────────────────────────────

func TestHMACHashDeterministic(t *testing.T) {
	data := []byte("api-key-raw")
	key := make([]byte, 32)

	h1 := crypto.HMACHash(data, key)
	h2 := crypto.HMACHash(data, key)

	if h1 != h2 {
		t.Fatal("HMACHash must be deterministic")
	}
	if h1 == "" {
		t.Fatal("HMACHash must not be empty")
	}
}

func TestHMACHashDifferentDataDifferentHash(t *testing.T) {
	key := make([]byte, 32)
	h1 := crypto.HMACHash([]byte("key-a"), key)
	h2 := crypto.HMACHash([]byte("key-b"), key)

	if h1 == h2 {
		t.Fatal("HMACHash of different data should differ")
	}
}

func TestHMACHashDifferentKeyDifferentHash(t *testing.T) {
	data := []byte("same-api-key")
	key1 := make([]byte, 32)
	key2 := make([]byte, 32)
	key2[0] = 0xFF

	h1 := crypto.HMACHash(data, key1)
	h2 := crypto.HMACHash(data, key2)

	if h1 == h2 {
		t.Fatal("HMACHash with different HMAC keys should differ")
	}
}

func TestHMACHashIsBase64(t *testing.T) {
	h := crypto.HMACHash([]byte("data"), make([]byte, 32))
	if _, err := base64.StdEncoding.DecodeString(h); err != nil {
		t.Fatalf("HMACHash output is not valid Base64: %v", err)
	}
}

// ─── GenerateKey ─────────────────────────────────────────────────────────────

func TestGenerateKeyLength(t *testing.T) {
	for _, n := range []int{16, 24, 32} {
		key, err := crypto.GenerateKey(n)
		if err != nil {
			t.Fatalf("GenerateKey(%d): %v", n, err)
		}
		if len(key) != n {
			t.Fatalf("GenerateKey(%d) returned %d bytes", n, len(key))
		}
	}
}

func TestGenerateKeyIsRandom(t *testing.T) {
	a, _ := crypto.GenerateKey(32)
	b, _ := crypto.GenerateKey(32)
	if bytes.Equal(a, b) {
		t.Error("GenerateKey should return different values on each call")
	}
}

func TestGenerateKeyNotAllZeros(t *testing.T) {
	key, _ := crypto.GenerateKey(32)
	allZero := true
	for _, b := range key {
		if b != 0 {
			allZero = false
			break
		}
	}
	if allZero {
		t.Error("GenerateKey returned all-zero key (extremely unlikely, indicates RNG issue)")
	}
}

// ─── Wire format ─────────────────────────────────────────────────────────────

func TestEncryptedOutputContainsNonce(t *testing.T) {
	key := make([]byte, 32)
	encoded, _ := crypto.Encrypt(key, []byte("test"))

	raw, _ := base64.StdEncoding.DecodeString(encoded)
	// Minimum: nonce(12) + tag(16) = 28 bytes
	if len(raw) < 28 {
		t.Fatalf("encrypted output too short: %d bytes", len(raw))
	}
}

func TestEncryptedOutputIsValidBase64(t *testing.T) {
	key := make([]byte, 32)
	encoded, _ := crypto.Encrypt(key, []byte("test"))

	if strings.ContainsAny(encoded, " \n\t") {
		t.Error("Base64 output should have no whitespace")
	}
	if _, err := base64.StdEncoding.DecodeString(encoded); err != nil {
		t.Fatalf("Encrypt output is not valid Base64: %v", err)
	}
}
