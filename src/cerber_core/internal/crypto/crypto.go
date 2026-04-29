// Package crypto provides AES-GCM-256 encrypt/decrypt and HMAC-SHA256 hashing.
// Wire format: Base64StdEncoding( Nonce[12] || Ciphertext || Tag[16] )
package crypto

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"io"
)

// Encrypt encrypts plaintext with AES-GCM-256 using key (must be 32 bytes).
// Returns Base64(nonce || ciphertext+tag).
func Encrypt(key, plaintext []byte) (string, error) {
	if len(key) != 32 {
		return "", errors.New("key must be 32 bytes")
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, gcm.NonceSize()) // 12 bytes
	if _, err = io.ReadFull(rand.Reader, nonce); err != nil {
		return "", err
	}
	// Seal appends ciphertext+tag to nonce slice
	sealed := gcm.Seal(nonce, nonce, plaintext, nil)
	return base64.StdEncoding.EncodeToString(sealed), nil
}

// Decrypt decodes Base64(nonce||ciphertext+tag) and returns plaintext.
func Decrypt(key []byte, encoded string) ([]byte, error) {
	if len(key) != 32 {
		return nil, errors.New("key must be 32 bytes")
	}
	data, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		return nil, err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	if len(data) < gcm.NonceSize() {
		return nil, errors.New("ciphertext too short")
	}
	nonce, ciphertext := data[:gcm.NonceSize()], data[gcm.NonceSize():]
	return gcm.Open(nil, nonce, ciphertext, nil)
}

// HMACHash returns Base64(HMAC-SHA256(data, key)).
// Used for deterministic API-key hashing — no salt needed because the master
// HMAC key is the secret.
func HMACHash(data, key []byte) string {
	mac := hmac.New(sha256.New, key)
	mac.Write(data)
	return base64.StdEncoding.EncodeToString(mac.Sum(nil))
}

// GenerateKey returns n cryptographically random bytes.
func GenerateKey(n int) ([]byte, error) {
	key := make([]byte, n)
	_, err := io.ReadFull(rand.Reader, key)
	return key, err
}
