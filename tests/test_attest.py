"""Claim-vs-execution layer: attest an agent's claim against observed execution."""

from __future__ import annotations

import json
import types

import pytest

from mizan import receipt_v0
from mizan.receipt import Receipt, StageRecord
from mizan.verify import cmd_verify

SECRET = "attest-secret"


def _execution_receipt():
    r = Receipt("book a flight", "ok")
    return r.to_v0(
        secret=SECRET, key_id="k", tool="book_flight",
        execution={
            "tool": "book_flight",
            "args_hash": receipt_v0.hash_value({"city": "RUH"}),
            "result_hash": receipt_v0.hash_value({"pnr": "OK123"}),
            "observed_status": "ok",
        },
    )


def test_attest_claim_verdicts():
    ex = {"tool": "t", "args_hash": "a", "result_hash": "r", "observed_status": "ok"}
    assert receipt_v0.attest_claim(ex, None) == "not_applicable"
    assert receipt_v0.attest_claim(None, {"tool": "t", "result_hash": "r"}) == "unverified"
    assert receipt_v0.attest_claim(ex, {"tool": "t", "result_hash": "r"}) == "verified"
    assert receipt_v0.attest_claim(ex, {"tool": "other", "result_hash": "r"}) == "tampered"
    assert receipt_v0.attest_claim(ex, {"tool": "t", "result_hash": "WRONG"}) == "tampered"
    assert receipt_v0.attest_claim(ex, {"tool": "t", "result_hash": None}) == "unverified"


def test_attest_honest_claim_is_verified():
    doc = receipt_v0.attest(_execution_receipt(), claimed_tool="book_flight",
                            claimed_result={"pnr": "OK123"}, secret=SECRET, key_id="k")
    assert doc["verification"] == "verified"
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.OK


def test_attest_lying_claim_is_tampered():
    doc = receipt_v0.attest(_execution_receipt(), claimed_tool="book_flight",
                            claimed_result={"pnr": "EVIL999"}, secret=SECRET, key_id="k")
    assert doc["verification"] == "tampered"
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.OK  # signature still valid


def test_to_v0_autocomputes_verification_without_a_verify_stage():
    r = Receipt("x", "y")  # no verify stage
    doc = r.to_v0(
        secret=SECRET,
        execution={"tool": "t", "args_hash": "a", "result_hash": "r", "observed_status": "ok"},
        claim={"tool": "t", "result_hash": "r"},
    )
    assert doc["verification"] == "verified"


def _verify(doc, *, allow_mismatch=False, tmp=None):
    path = (tmp or "/tmp") + "/_attest_test.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    import os
    os.environ["MIZAN_RECEIPT_SECRET"] = SECRET
    return cmd_verify(types.SimpleNamespace(
        receipt=path, secret_env="MIZAN_RECEIPT_SECRET",
        allow_unsigned=False, allow_claim_mismatch=allow_mismatch))


def test_cli_exit_codes_for_claim(tmp_path):
    honest = receipt_v0.attest(_execution_receipt(), claimed_tool="book_flight",
                               claimed_result={"pnr": "OK123"}, secret=SECRET, key_id="k")
    liar = receipt_v0.attest(_execution_receipt(), claimed_tool="book_flight",
                             claimed_result={"pnr": "EVIL999"}, secret=SECRET, key_id="k")
    assert _verify(honest, tmp=str(tmp_path)) == 0
    assert _verify(liar, tmp=str(tmp_path)) == 5            # claim mismatch
    assert _verify(liar, allow_mismatch=True, tmp=str(tmp_path)) == 0


def _doc_with(verification, *, match, tmp):
    """A signed receipt whose execution and claim (mis)match, with an explicit
    (possibly inconsistent) verification field."""
    real = receipt_v0.hash_value({"r": "REAL"})
    claim_hash = real if match else receipt_v0.hash_value({"r": "LIE"})
    return Receipt("x", "y").to_v0(
        secret=SECRET,
        execution={"tool": "t", "args_hash": receipt_v0.hash_value("a"),
                   "result_hash": real, "observed_status": "ok"},
        claim={"tool": "t", "result_hash": claim_hash},
        verification=verification,
    )


@pytest.mark.parametrize("declared", ["unverified", "not_applicable", "tampered"])
def test_mismatch_is_exit_5_regardless_of_declared_field(declared, tmp_path):
    # A receipt cannot hide a lie behind a self-declared 'unverified'/'not_applicable'.
    doc = _doc_with(declared, match=False, tmp=str(tmp_path))
    assert _verify(doc, tmp=str(tmp_path)) == 5


def test_mismatch_declared_verified_is_exit_1(tmp_path):
    doc = _doc_with("verified", match=False, tmp=str(tmp_path))
    assert _verify(doc, tmp=str(tmp_path)) == 1  # forged positive verdict


@pytest.mark.parametrize("declared", ["unverified", "verified"])
def test_match_is_exit_0_even_if_field_understates(declared, tmp_path):
    doc = _doc_with(declared, match=True, tmp=str(tmp_path))
    assert _verify(doc, tmp=str(tmp_path)) == 0  # recomputed match is authoritative


def test_cli_detects_dishonest_forged_verified(tmp_path):
    liar = receipt_v0.attest(_execution_receipt(), claimed_tool="book_flight",
                             claimed_result={"pnr": "EVIL999"}, secret=SECRET, key_id="k")
    # forge verification=verified and re-sign with the same secret
    liar["verification"] = "verified"
    liar["signature"]["value"] = receipt_v0.sign(liar, SECRET)
    assert _verify(liar, tmp=str(tmp_path)) == 1            # dishonest -> invalid
