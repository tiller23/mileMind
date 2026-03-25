"""Tests for Fernet token encryption/decryption."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from src.services.crypto import decrypt_token, encrypt_token, generate_key


class TestEncryptToken:
    """Tests for encrypt_token()."""

    def test_encrypt_returns_different_from_plaintext(self) -> None:
        key = Fernet.generate_key().decode()
        plaintext = "test-access-token-12345"
        ciphertext = encrypt_token(plaintext, key)
        assert ciphertext != plaintext
        assert len(ciphertext) > len(plaintext)

    def test_encrypt_empty_raises(self) -> None:
        key = Fernet.generate_key().decode()
        with pytest.raises(ValueError, match="empty"):
            encrypt_token("", key)

    def test_encrypt_invalid_key_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid encryption key"):
            encrypt_token("test", "not-a-valid-key")


class TestDecryptToken:
    """Tests for decrypt_token()."""

    def test_decrypt_empty_raises(self) -> None:
        key = Fernet.generate_key().decode()
        with pytest.raises(ValueError, match="empty"):
            decrypt_token("", key)

    def test_decrypt_wrong_key_raises(self) -> None:
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()
        ciphertext = encrypt_token("secret", key1)
        with pytest.raises(ValueError, match="wrong key"):
            decrypt_token(ciphertext, key2)

    def test_decrypt_corrupted_data_raises(self) -> None:
        key = Fernet.generate_key().decode()
        with pytest.raises(ValueError):
            decrypt_token("not-valid-ciphertext", key)


class TestRoundTrip:
    """Tests for encrypt → decrypt round trips."""

    def test_round_trip_basic(self) -> None:
        key = Fernet.generate_key().decode()
        original = "strava-access-token-abc123"
        assert decrypt_token(encrypt_token(original, key), key) == original

    def test_round_trip_long_token(self) -> None:
        key = Fernet.generate_key().decode()
        original = "a" * 1000
        assert decrypt_token(encrypt_token(original, key), key) == original

    def test_round_trip_special_chars(self) -> None:
        key = Fernet.generate_key().decode()
        original = "token/with+special=chars&more"
        assert decrypt_token(encrypt_token(original, key), key) == original

    def test_different_encryptions_produce_different_ciphertext(self) -> None:
        """Fernet uses random IV, so same plaintext produces different ciphertext."""
        key = Fernet.generate_key().decode()
        plaintext = "same-token"
        ct1 = encrypt_token(plaintext, key)
        ct2 = encrypt_token(plaintext, key)
        assert ct1 != ct2
        assert decrypt_token(ct1, key) == plaintext
        assert decrypt_token(ct2, key) == plaintext


class TestGenerateKey:
    """Tests for generate_key()."""

    def test_generates_valid_fernet_key(self) -> None:
        key = generate_key()
        assert isinstance(key, str)
        # Should be usable for encrypt/decrypt
        ct = encrypt_token("test", key)
        assert decrypt_token(ct, key) == "test"

    def test_generates_unique_keys(self) -> None:
        keys = {generate_key() for _ in range(10)}
        assert len(keys) == 10
