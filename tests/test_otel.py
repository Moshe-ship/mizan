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


def test_tamper_in_nested_stage_detail_breaks_verification():
    good = Receipt(input="x", output="x").with_stage(
        StageRecord(stage=STAGE_VERIFY, tool="toolproof", ok=True, detail={"verdict": "VERIFIED"}))
    sig = good.signature("k")
    tampered = Receipt(input="x", output="x").with_stage(
        StageRecord(stage=STAGE_VERIFY, tool="toolproof", ok=True, detail={"verdict": "UNVERIFIED"}))
    assert not tampered.verify_signature("k", sig)


def test_key_id_carried_when_given():
    spans = receipt_to_spans(_receipt(), secret="k", key_id="prod-1")
    assert spans[0]["attributes"]["mizan.receipt.key_id"] == "prod-1"


def test_mizan_operation_name_preserved_alongside_genai():
    spans = receipt_to_spans(_receipt())
    for s in spans:
        assert s["attributes"]["mizan.operation.name"].startswith("mizan.")
        assert "gen_ai.operation.name" in s["attributes"]


# --- emit() sets real span status (fake tracer) --------------------------- #

class _FakeSpan:
    def __init__(self):
        self.attrs: dict = {}
        self.status = None
        self.events: list = []

    def set_attribute(self, k, v):
        self.attrs[k] = v

    def set_status(self, s):
        self.status = s

    def add_event(self, name, attributes=None):
        self.events.append((name, attributes))


class _FakeTracer:
    def __init__(self):
        self.spans: list = []

    def start_as_current_span(self, name):
        import contextlib

        sp = _FakeSpan()
        self.spans.append((name, sp))

        @contextlib.contextmanager
        def _cm():
            yield sp

        return _cm()


def test_emit_sets_error_status_on_failed_stage():
    from mizan import emit_otel

    tracer = _FakeTracer()
    emit_otel(_receipt(), tracer=tracer)
    by_name = {n: sp for n, sp in tracer.spans}
    # parent + verify failed -> status set; ok stages -> status None
    assert by_name["mizan.pipeline"].status is not None
    assert by_name["mizan.verify"].status is not None
    assert by_name["mizan.scan"].status is None
