"""Tests for the Receipt v0 evidence layer: projection, signing, validation, CLI."""

from __future__ import annotations

import json
import types

import pytest

import fixtures_gen
from mizan import receipt_v0
from mizan.receipt import Receipt, StageRecord

SECRET = "test-secret"


def _clean_receipt() -> Receipt:
    return Receipt(
        input="book a flight",
        output="ok",
        stages=(
            StageRecord("scan", "mcpscan", True, 0, {"findings": 0}),
            StageRecord("verify", "toolproof", True, 0, {"verdict": "VERIFIED"}),
        ),
    )


# --------------------------- projection & schema --------------------------- #
def test_to_v0_is_schema_valid_and_signed():
    doc = _clean_receipt().to_v0(secret=SECRET, key_id="k1")
    assert receipt_v0.structural_errors(doc) == []
    assert receipt_v0.full_validation_errors(doc) in (None, [])  # None if jsonschema absent
    assert doc["schema_version"] == "mizan.receipt/0"
    assert doc["signature"]["algorithm"] == "HMAC-SHA256"
    assert len(doc["signature"]["value"]) == 64


def test_roundtrip_sign_then_verify_ok():
    doc = _clean_receipt().to_v0(secret=SECRET)
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.OK


def test_decision_blocked_when_a_stage_refuses():
    r = Receipt("x", "", stages=(StageRecord("scan", "mcpscan", False, 0, {"rule": "R-BIDI-001"}),))
    doc = r.to_v0(secret=SECRET)
    assert doc["decision"]["action"] == "blocked"
    assert doc["verification"] == "not_applicable"


def test_decision_escalated_when_classify_escalates():
    r = Receipt("x", "y", stages=(StageRecord("classify", "qadiya", True, 0, {"escalated": True}),))
    assert r.to_v0(secret=SECRET)["decision"]["action"] == "escalated"


def test_verification_derived_from_verify_verdict():
    for verdict, expected in [("VERIFIED", "verified"), ("UNVERIFIED", "unverified"), ("TAMPERED", "tampered")]:
        r = Receipt("x", "y", stages=(StageRecord("verify", "toolproof", True, 0, {"verdict": verdict}),))
        assert r.to_v0(secret=SECRET)["verification"] == expected


# ------------------------------- tampering -------------------------------- #
def test_tamper_after_signing_is_detected():
    doc = _clean_receipt().to_v0(secret=SECRET)
    doc["output"]["hash"] = receipt_v0.hash_text("different")
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.TAMPERED


def test_wrong_secret_fails():
    doc = _clean_receipt().to_v0(secret=SECRET)
    assert receipt_v0.verify(doc, "wrong-secret") == receipt_v0.TAMPERED


def test_unsigned_receipt():
    doc = _clean_receipt().to_v0()  # no secret
    assert doc["signature"]["value"] is None
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.UNSIGNED
    assert receipt_v0.structural_errors(doc) == []  # unsigned is still structurally valid


# --------------------------- structural validation ------------------------ #
def test_missing_required_field_is_caught():
    doc = _clean_receipt().to_v0(secret=SECRET)
    del doc["decision"]
    errs = receipt_v0.structural_errors(doc)
    assert any("decision" in e for e in errs)


def test_bad_schema_version_is_caught():
    doc = _clean_receipt().to_v0(secret=SECRET)
    doc["schema_version"] = "mizan.receipt/99"
    assert any("schema_version" in e for e in receipt_v0.structural_errors(doc))


# ----------------------------- canonicalization --------------------------- #
def test_canonical_rejects_floats():
    with pytest.raises(ValueError):
        receipt_v0.canonicalize({"x": 1.5})


def test_signature_is_key_order_independent():
    a = {"b": 1, "a": 2, "signature": {"value": None}}
    b = {"a": 2, "b": 1, "signature": {"value": None}}
    assert receipt_v0.sign(a, SECRET) == receipt_v0.sign(b, SECRET)


# ------------------------------- redaction -------------------------------- #
def test_redaction_default_hides_summary():
    doc = _clean_receipt().to_v0(secret=SECRET)  # redact=True default
    assert doc["input"]["summary"] is None
    assert doc["input"]["hash"].startswith("sha256:")


def test_no_redaction_keeps_summary():
    doc = _clean_receipt().to_v0(secret=SECRET, redact=False)
    assert doc["input"]["summary"] == "book a flight"


# --------------------------- example fixtures drift ----------------------- #
@pytest.mark.parametrize("name", ["passed", "blocked", "tampered"])
def test_committed_examples_match_generator(name):
    import pathlib
    built = fixtures_gen.build()[name]
    committed = json.loads(
        (pathlib.Path(__file__).resolve().parent.parent / "examples" / "receipts" / f"{name}.json").read_text()
    )
    assert committed == built, "examples/receipts is stale — run `python tests/fixtures_gen.py`"


# --------------------------------- CLI ------------------------------------ #
def _example_path(name):
    import pathlib
    return str(pathlib.Path(__file__).resolve().parent.parent / "examples" / "receipts" / f"{name}.json")


def test_cli_verify_passed(monkeypatch, capsys):
    from mizan.verify import cmd_verify
    monkeypatch.setenv("MIZAN_RECEIPT_SECRET", fixtures_gen.SECRET)
    args = types.SimpleNamespace(receipt=_example_path("passed"), secret_env="MIZAN_RECEIPT_SECRET", allow_unsigned=False)
    assert cmd_verify(args) == 0
    assert "VALID" in capsys.readouterr().out


def test_cli_verify_tampered_exit_2(monkeypatch):
    from mizan.verify import cmd_verify
    monkeypatch.setenv("MIZAN_RECEIPT_SECRET", fixtures_gen.SECRET)
    args = types.SimpleNamespace(receipt=_example_path("tampered"), secret_env="MIZAN_RECEIPT_SECRET", allow_unsigned=False)
    assert cmd_verify(args) == 2


def test_cli_diff_same_and_different():
    from mizan.verify import cmd_diff
    same = types.SimpleNamespace(a=_example_path("passed"), b=_example_path("passed"), include_volatile=False)
    assert cmd_diff(same) == 0
    diff = types.SimpleNamespace(a=_example_path("passed"), b=_example_path("blocked"), include_volatile=False)
    assert cmd_diff(diff) == 1
