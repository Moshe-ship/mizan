"""mizan.otel — export a Receipt as OpenTelemetry-compatible spans.

Scope (deliberately narrow): map the existing :class:`~mizan.receipt.Receipt`
to OTel GenAI-style spans/events. This is an *exporter*, not a new spec and
not an observability framework. It rides the converging OTel GenAI semantic
conventions for interop (Datadog/Honeycomb/LangChain emit the same shape) and
adds the one thing OTel does not provide: a tamper-evident receipt signature.

`receipt_to_spans` is pure (no SDK dependency) and fully testable. `emit`
optionally pushes real spans through an OpenTelemetry tracer when the SDK is
installed (`pip install mizan[otel]`).
"""

from __future__ import annotations

from typing import Any, Optional

from mizan.receipt import Receipt

# Map a Mizan stage to an OTel GenAI operation name where one applies;
# reliability-specific stages keep a mizan.* operation name.
_OP_NAME = {
    "scan": "mizan.scan",
    "restore": "mizan.restore",
    "balance": "mizan.balance",
    "classify": "gen_ai.execute_tool",   # gating a tool call
    "constrain": "gen_ai.execute_tool",
    "verify": "mizan.verify",
}


def receipt_to_spans(receipt: Receipt, *, secret: Optional[str] = None) -> list[dict[str, Any]]:
    """Return OTel-shaped span dicts: one parent + one child per stage.

    Attribute names use `gen_ai.*` where the GenAI conventions apply and
    `mizan.*` for the reliability-specific signal. If `secret` is given, the
    parent span carries `mizan.receipt.signature` (HMAC) — the tamper-evidence
    layer OTel lacks.
    """
    parent_id = "mizan.pipeline"
    parent_attrs: dict[str, Any] = {
        "gen_ai.operation.name": "mizan.pipeline",
        "mizan.receipt.ok": receipt.ok,
        "mizan.receipt.blocked_by": list(receipt.blocked_by),
        "mizan.receipt.stage_count": len(receipt.stages),
    }
    if secret is not None:
        parent_attrs["mizan.receipt.signature"] = receipt.signature(secret)
        parent_attrs["mizan.receipt.sig_alg"] = "HMAC-SHA256"

    parent = {
        "name": "mizan.pipeline",
        "span_id": parent_id,
        "parent_span_id": None,
        "kind": "INTERNAL",
        "status": "OK" if receipt.ok else "ERROR",
        "attributes": parent_attrs,
        "events": [],
    }

    spans = [parent]
    for i, s in enumerate(receipt.stages):
        attrs: dict[str, Any] = {
            "gen_ai.operation.name": _OP_NAME.get(s.stage, f"mizan.{s.stage}"),
            "mizan.stage": s.stage,
            "mizan.tool": s.tool,
            "mizan.stage.ok": s.ok,
            "mizan.stage.changes": s.changes,
        }
        events = []
        if not s.ok:
            events.append({
                "name": "mizan.finding",
                "attributes": {"mizan.stage": s.stage, "mizan.tool": s.tool, **_flatten(s.detail)},
            })
        spans.append({
            "name": f"mizan.{s.stage}",
            "span_id": f"{parent_id}.{i}.{s.stage}",
            "parent_span_id": parent_id,
            "kind": "INTERNAL",
            "status": "OK" if s.ok else "ERROR",
            "attributes": attrs,
            "events": events,
        })
    return spans


def _flatten(detail: Any, prefix: str = "mizan.detail") -> dict[str, Any]:
    """Flatten a small detail dict into OTel-safe scalar attributes."""
    out: dict[str, Any] = {}
    if isinstance(detail, dict):
        for k, v in detail.items():
            key = f"{prefix}.{k}"
            if isinstance(v, (str, bool, int, float)):
                out[key] = v
            else:
                out[key] = str(v)[:200]
    return out


def emit(receipt: Receipt, tracer: Any = None, *, secret: Optional[str] = None) -> list[dict[str, Any]]:
    """Emit real OTel spans if a tracer (or the SDK) is available; always
    returns the span dicts. No-op-safe when the SDK is absent."""
    spans = receipt_to_spans(receipt, secret=secret)
    if tracer is None:
        try:
            from opentelemetry import trace  # type: ignore

            tracer = trace.get_tracer("mizan")
        except Exception:  # noqa: BLE001
            return spans  # SDK not installed — return the mapping only

    # Parent then children, preserving nesting.
    parent = spans[0]
    with tracer.start_as_current_span(parent["name"]) as ps:
        for k, v in parent["attributes"].items():
            ps.set_attribute(k, v)
        for child in spans[1:]:
            with tracer.start_as_current_span(child["name"]) as cs:
                for k, v in child["attributes"].items():
                    cs.set_attribute(k, v)
                for ev in child["events"]:
                    cs.add_event(ev["name"], attributes=ev["attributes"])
    return spans
