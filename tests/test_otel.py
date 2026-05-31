"""Tests for the OTel exporter and receipt signing."""

from __future__ import annotations

from mizan import receipt_to_spans
from mizan.receipt import Receipt, StageRecord, STAGE_SCAN, STAGE_VERIFY


def _receipt() -> Receipt:
    r = Receipt(input="x", output="x")
    r = r.with_stage(StageRecord(stage=STAGE_SCAN, tool="mizan.mcpscan", ok=True))
    r = r.with_stage(StageRecord(stage=STAGE_VERIFY, tool="toolproof", ok=False,
                                 detail={"verdict": "UNVERIFIED"}))
    return r


def test_signature_is_stable_and_verifies():
    r = _receipt()
    sig = r.signature("secret")
    assert sig == r.signature("secret")          # deterministic
    assert r.verify_signature("secret", sig)
    assert not r.verify_signature("wrong", sig)


def test_signature_changes_with_content():
    a = Receipt(input="a", output="a")
    b = Receipt(input="b", output="b")
    assert a.signature("k") != b.signature("k")


def test_spans_have_parent_and_one_child_per_stage():
    spans = receipt_to_spans(_receipt())
    parent = spans[0]
    children = spans[1:]
    assert parent["parent_span_id"] is None
    assert len(children) == 2
    assert all(c["parent_span_id"] == parent["span_id"] for c in children)


def test_genai_operation_attribute_present():
    spans = receipt_to_spans(_receipt())
    for s in spans:
        assert "gen_ai.operation.name" in s["attributes"]


def test_failed_stage_maps_to_error_status_and_event():
    spans = receipt_to_spans(_receipt())
    verify = next(s for s in spans if s["attributes"].get("mizan.stage") == "verify")
    assert verify["status"] == "ERROR"
    assert any(e["name"] == "mizan.finding" for e in verify["events"])


def test_signature_attribute_present_when_secret_given():
    spans = receipt_to_spans(_receipt(), secret="k")
    assert "mizan.receipt.signature" in spans[0]["attributes"]
    assert spans[0]["attributes"]["mizan.receipt.sig_alg"] == "HMAC-SHA256"


def test_no_signature_attribute_without_secret():
    spans = receipt_to_spans(_receipt())
    assert "mizan.receipt.signature" not in spans[0]["attributes"]
