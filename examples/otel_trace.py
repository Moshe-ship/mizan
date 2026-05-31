"""One example trace: scan -> preflight -> gate -> constrain -> verify, mapped
to OTel-compatible spans with a signed receipt.

Run:  python examples/otel_trace.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

for _name in ("mizan", "jabr", "muqabalah", "qadiya", "mtg", "toolproof"):
    _c = Path.home() / "Projects" / _name
    if _c.is_dir() and str(_c) not in sys.path:
        sys.path.insert(0, str(_c))

import mtg  # noqa: E402
import toolproof as tp  # noqa: E402

from mizan import (  # noqa: E402
    PreflightContext, ToolGate, constrain, equals_constraint, preflight,
    record_from_toolproof, receipt_to_spans, scan_tool,
)

SECRET = "demo-secret"
GATE = ToolGate([equals_constraint("tool", "tool_name", ["book_flight"])],
                allowed_case_ids=["tool=book_flight"])
CITY_SPEC = mtg.GuardSpec(
    slot_type="city", script="ar", dialect_expected=None, dialect_enforcement="off",
    transliteration_allowed=False, morphologically_productive=False,
    canonicalization="nfc", canonical_form_required=False, mode="advisory",
    post_call_contract=None,
)


def run() -> None:
    # 0) scan the tool surface
    r = scan_tool({"name": "book_flight", "description": "Books a flight to a city."}).to_stage_record()
    # 1+2) preflight
    pf = preflight("احجز رحلة إلى الرياض", PreflightContext())
    receipt = pf.receipt.with_stage(r)  # carry the scan stage in
    # 3) gate
    receipt = receipt.with_stage(GATE.check({"tool_name": "book_flight", "args": {}}).record)
    # 4) constrain the Arabic arg
    crec, _ = constrain("الرياض", CITY_SPEC)
    receipt = receipt.with_stage(crec)
    # 5) verify (real toolproof)
    store = tp.ReceiptStore(); proxy = tp.ToolProxy(store, SECRET)
    resp = {"confirmation": "OK123"}
    proxy.record("book_flight", {"city": "الرياض"}, resp)
    v = tp.Verifier(store, SECRET).verify_claim(tp.AgentClaim("book_flight", {"city": "الرياض"}, resp))
    receipt = receipt.with_stage(record_from_toolproof(v))

    spans = receipt_to_spans(receipt, secret=SECRET, key_id="demo-key-1")
    print(f"receipt ok={receipt.ok}  key_id=demo-key-1  signature={receipt.signature(SECRET)[:16]}…\n")
    for s in spans:
        ind = "" if s["parent_span_id"] is None else "  └─ "
        print(f"{ind}{s['name']:22} [{s['status']:5}] {s['attributes'].get('gen_ai.operation.name')}")
    print("\nfull parent span:")
    print(json.dumps(spans[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    run()
