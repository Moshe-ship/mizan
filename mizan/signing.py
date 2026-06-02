"""Pluggable receipt signers.

- **HMAC-SHA256** (default, zero-dependency): symmetric — the verifier needs the
  same secret that can sign. Fine for internal logs / a single trust domain.
- **Ed25519** (`pip install "mizan[ed25519]"`): asymmetric — the signer holds the
  private key, an auditor verifies with only the **public** key. This is the
  cross-party "signed action truth" model: verification does not hand out signing
  authority, and `key_id` + key rotation become meaningful.

Both sign the same RFC 8785-aligned canonical bytes (the receipt minus its
`signature`), so the algorithm is just a swap in the signature envelope.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional

HMAC_SHA256 = "HMAC-SHA256"
ED25519 = "Ed25519"


class HmacSigner:
    """Symmetric HMAC-SHA256 signer (default, no dependencies)."""

    algorithm = HMAC_SHA256

    def __init__(self, secret: str, key_id: Optional[str] = None) -> None:
        self._secret = secret.encode("utf-8")
        self.key_id = key_id

    def sign(self, message: bytes) -> str:
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()


def _ed25519():
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
    except Exception as exc:  # noqa: BLE001
        raise ImportError(
            "Ed25519 signing/verification needs the 'cryptography' package: "
            "pip install 'mizan[ed25519]'"
        ) from exc
    return Ed25519PrivateKey, Ed25519PublicKey


def _raw():
    from cryptography.hazmat.primitives import serialization

    return serialization


class Ed25519Signer:
    """Asymmetric Ed25519 signer. Private key is a 32-byte seed, hex-encoded."""

    algorithm = ED25519

    def __init__(self, private_key_hex: str, key_id: Optional[str] = None) -> None:
        Priv, _ = _ed25519()
        self._key = Priv.from_private_bytes(bytes.fromhex(private_key_hex))
        self.key_id = key_id

    def sign(self, message: bytes) -> str:
        return self._key.sign(message).hex()

    def public_key_hex(self) -> str:
        s = _raw()
        raw = self._key.public_key().public_bytes(s.Encoding.Raw, s.PublicFormat.Raw)
        return raw.hex()

    def private_key_hex(self) -> str:
        s = _raw()
        return self._key.private_bytes(
            s.Encoding.Raw, s.PrivateFormat.Raw, s.NoEncryption()
        ).hex()

    @classmethod
    def generate(cls, key_id: Optional[str] = None) -> "Ed25519Signer":
        Priv, _ = _ed25519()
        s = _raw()
        priv_hex = Priv.generate().private_bytes(
            s.Encoding.Raw, s.PrivateFormat.Raw, s.NoEncryption()
        ).hex()
        return cls(priv_hex, key_id=key_id)


class MissingKeyError(ValueError):
    """No verification key was supplied for the receipt's algorithm."""


def verify_signature(
    algorithm: str,
    message: bytes,
    value: str,
    *,
    secret: Optional[str] = None,
    public_key_hex: Optional[str] = None,
) -> bool:
    """Verify a signature `value` over `message` under `algorithm`.

    Raises ``MissingKeyError`` if the required key is absent, ``ValueError`` for
    an unknown algorithm.
    """
    if algorithm == HMAC_SHA256:
        if secret is None:
            raise MissingKeyError("HMAC verification needs the secret")
        expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, value)
    if algorithm == ED25519:
        if public_key_hex is None:
            raise MissingKeyError("Ed25519 verification needs the public key")
        _, Pub = _ed25519()
        from cryptography.exceptions import InvalidSignature

        try:
            Pub.from_public_bytes(bytes.fromhex(public_key_hex)).verify(
                bytes.fromhex(value), message
            )
            return True
        except (InvalidSignature, ValueError):
            return False
    raise ValueError(f"unknown signature algorithm: {algorithm!r}")
