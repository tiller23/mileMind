"""Symmetric encryption for sensitive tokens stored at rest.

Uses Fernet (AES-128-CBC with HMAC-SHA256) from the cryptography library.
Tokens are encrypted before writing to the database and decrypted on read.

Usage:
    from src.services.crypto import encrypt_token, decrypt_token
    ciphertext = encrypt_token("secret", key)
    plaintext = decrypt_token(ciphertext, key)
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


def encrypt_token(plaintext: str, key: str) -> str:
    """Encrypt a plaintext token using Fernet symmetric encryption.

    Args:
        plaintext: The token value to encrypt.
        key: Fernet-compatible base64 key (use Fernet.generate_key()).

    Returns:
        Base64-encoded ciphertext string.

    Raises:
        ValueError: If plaintext is empty or key is invalid.
    """
    if not plaintext:
        raise ValueError("Cannot encrypt empty token")
    try:
        f = Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as exc:
        raise ValueError(f"Invalid encryption key: {exc}") from exc
    return f.encrypt(plaintext.encode()).decode()


def decrypt_token(ciphertext: str, key: str) -> str:
    """Decrypt a Fernet-encrypted token.

    Args:
        ciphertext: Base64-encoded ciphertext from encrypt_token().
        key: Same Fernet key used for encryption.

    Returns:
        Original plaintext token.

    Raises:
        ValueError: If ciphertext is empty, key is invalid, or decryption fails.
    """
    if not ciphertext:
        raise ValueError("Cannot decrypt empty ciphertext")
    try:
        f = Fernet(key.encode() if isinstance(key, str) else key)
        return f.decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Decryption failed — wrong key or corrupted data") from exc
    except Exception as exc:
        raise ValueError(f"Invalid encryption key: {exc}") from exc


def generate_key() -> str:
    """Generate a new Fernet encryption key.

    Returns:
        Base64-encoded key string suitable for STRAVA_TOKEN_ENCRYPTION_KEY.
    """
    return Fernet.generate_key().decode()
