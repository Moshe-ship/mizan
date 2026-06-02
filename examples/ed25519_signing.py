"""Asymmetric receipts: sign with a private key, verify with only the public key.

HMAC proves "whoever holds the shared secret signed this". Ed25519 proves *who*
signed it and lets a third party verify **without** the signing key — the
cross-party "signed action truth" model.

    pip install "mizan[ed25519]"
    python examples/ed25519_signing.py

The keypair here is generated at runtime and is demo-only. In production, keep
the private key in a secret manager / file with 0600 perms (see `mizan keygen`),
and distribute only the public key.
"""

from __future__ import annotations

from mizan import receipt_v0
from mizan.receipt import Receipt, StageRecord
from mizan.signing import Ed25519Signer


def main() -> None:
    # The signer holds the private key. (Demo-only — generated fresh each run.)
    signer = Ed25519Signer.generate(key_id="demo-key-1")
    public_key = signer.public_key_hex()  # this is all an auditor needs

    receipt = Receipt(
        "book a flight",
        "ok",
        stages=(StageRecord("verify", "adapter", ok=True, detail={"verdict": "VERIFIED"}),),
    )
    doc = receipt.to_v0(
        signer=signer, tool="book_flight",
        execution={"tool": "book_flight", "args_hash": receipt_v0.hash_value({"city": "RUH"}),
                   "result_hash": receipt_v0.hash_value({"pnr": "OK123"}), "observed_status": "ok"},
        claim={"tool": "book_flight", "result_hash": receipt_v0.hash_value({"pnr": "OK123"})},
    )

    print(f"signed with Ed25519 (key_id={doc['signature']['key_id']})")
    print(f"  public key (share this): {public_key}")
    print(f"  verify with public key only: {receipt_v0.verify(doc, public_key=public_key)}")

    # An auditor with a DIFFERENT (wrong) key cannot validate it.
    wrong = Ed25519Signer.generate().public_key_hex()
    print(f"  with the wrong public key:   {receipt_v0.verify(doc, public_key=wrong)}")

    # Tamper after signing → fails, even though the verifier never had the private key.
    doc["execution"]["result_hash"] = receipt_v0.hash_value({"pnr": "REFUNDED"})
    print(f"  after tampering:             {receipt_v0.verify(doc, public_key=public_key)}")


if __name__ == "__main__":
    main()
