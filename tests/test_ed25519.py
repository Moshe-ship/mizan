"""Ed25519 asymmetric signing: verify with the public key only, HMAC unchanged."""

from __future__ import annotations

import json
import types

import pytest

pytest.importorskip("cryptography")

from mizan import receipt_v0
from mizan.receipt import Receipt
from mizan.signing import Ed25519Signer, HmacSigner
from mizan.verify import cmd_keygen, cmd_verify


def _exec_receipt(signer):
    return Receipt("book a flight", "ok").to_v0(
        signer=signer, tool="book_flight",
        execution={"tool": "book_flight", "args_hash": receipt_v0.hash_value("a"),
                   "result_hash": receipt_v0.hash_value("R"), "observed_status": "ok"},
    )


def test_ed25519_signs_and_verifies_with_public_key_only():
    signer = Ed25519Signer.generate(key_id="prod-1")
    doc = _exec_receipt(signer)
    assert doc["signature"]["algorithm"] == "Ed25519"
    assert doc["signature"]["key_id"] == "prod-1"
    assert len(doc["signature"]["value"]) == 128
    assert receipt_v0.structural_errors(doc) == []
    # the auditor needs only the public key — never the signing key
    assert receipt_v0.verify(doc, public_key=signer.public_key_hex()) == receipt_v0.OK


def test_ed25519_tampered_fails():
    signer = Ed25519Signer.generate()
    doc = _exec_receipt(signer)
    doc["output"]["hash"] = receipt_v0.hash_text("changed")
    assert receipt_v0.verify(doc, public_key=signer.public_key_hex()) == receipt_v0.TAMPERED


def test_ed25519_wrong_public_key_fails():
    signer = Ed25519Signer.generate()
    doc = _exec_receipt(signer)
    other = Ed25519Signer.generate().public_key_hex()
    assert receipt_v0.verify(doc, public_key=other) == receipt_v0.TAMPERED


def test_ed25519_missing_public_key_is_no_secret():
    signer = Ed25519Signer.generate()
    doc = _exec_receipt(signer)
    assert receipt_v0.verify(doc) == receipt_v0.NO_SECRET


def test_hmac_unchanged():
    doc = Receipt("x", "y").to_v0(secret="s")
    assert doc["signature"]["algorithm"] == "HMAC-SHA256"
    assert receipt_v0.verify(doc, "s") == receipt_v0.OK
    assert receipt_v0.verify(doc, "wrong") == receipt_v0.TAMPERED


def test_ed25519_claim_mismatch_still_exits_5(tmp_path, monkeypatch):
    signer = Ed25519Signer.generate(key_id="k")
    execution = _exec_receipt(signer)
    liar = receipt_v0.attest(execution, claimed_tool="book_flight",
                             claimed_result="A-LIE", signer=signer)
    assert liar["verification"] == "tampered"
    assert receipt_v0.verify(liar, public_key=signer.public_key_hex()) == receipt_v0.OK  # sig valid

    pub = tmp_path / "key.pub"
    pub.write_text(signer.public_key_hex())
    path = tmp_path / "liar.json"
    path.write_text(json.dumps(liar))
    code = cmd_verify(types.SimpleNamespace(
        receipt=str(path), secret_env="MIZAN_RECEIPT_SECRET", public_key=str(pub),
        allow_unsigned=False, allow_claim_mismatch=False))
    assert code == 5  # signature passes, claim mismatch → 5


def test_cli_keygen_and_verify_roundtrip(tmp_path, monkeypatch):
    keyfile = tmp_path / "key.json"
    assert cmd_keygen(types.SimpleNamespace(key_id="prod-1", out=str(keyfile))) == 0
    kp = json.loads(keyfile.read_text())
    assert kp["algorithm"] == "Ed25519" and len(kp["public_key"]) == 64

    signer = Ed25519Signer(kp["private_key"], key_id=kp["key_id"])
    doc = Receipt("x", "ok").to_v0(signer=signer)
    rpath = tmp_path / "r.json"
    rpath.write_text(json.dumps(doc))

    # verify with the keygen JSON as --public-key
    code = cmd_verify(types.SimpleNamespace(
        receipt=str(rpath), secret_env="MIZAN_RECEIPT_SECRET", public_key=str(keyfile),
        allow_unsigned=False, allow_claim_mismatch=False))
    assert code == 0
    # without a key → no-secret exit 4
    code = cmd_verify(types.SimpleNamespace(
        receipt=str(rpath), secret_env="MIZAN_RECEIPT_SECRET", public_key=None,
        allow_unsigned=False, allow_claim_mismatch=False))
    assert code == 4
