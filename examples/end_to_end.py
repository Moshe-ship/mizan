"""End-to-end Mizan demo: one Receipt across all five stages.

Runs a proposed tool call through the whole scale and accretes a single
weighable receipt:

    restore (jabr) -> balance (muqabalah) -> classify/gate (qadiya)
        -> constrain (mtg) -> verify (toolproof)

Two scenarios: a clean Arabic request that survives every stage, and a
failure path (transliterated argument + a hallucinated tool claim) that the
scale catches. Requires mtg and toolproof on the path; in a dev tree this
file adds the local checkouts under ~/Projects automatically.

Run:  python examples/end_to_end.py
"""

from __future__ import annotations

import sys
from pathlib import Path

for _name in ("mizan", "jabr", "muqabalah", "qadiya", "mtg", "toolproof"):
    _c = Path.home() / "Projects" / _name
    if _c.is_dir() and str(_c) not in sys.path:
        sys.path.insert(0, str(_c))

import mtg  # noqa: E402
import toolproof as tp  # noqa: E402

from mizan import (  # noqa: E402
    PreflightContext,
    ToolGate,
    constrain,
    equals_constraint,
    preflight,
    record_from_toolproof,
)

SECRET = "demo-secret"

# A gate that allows two tools; everything else is escalated.
GATE = ToolGate(
    [equals_constraint("tool", "tool_name", ["book_flight", "search"])],
    allowed_case_ids=["tool=book_flight", "tool=search"],
)

# A guard: the city argument must stay in Arabic script, no transliteration.
CITY_SPEC = mtg.GuardSpec(
    slot_type="city", script="ar", dialect_expected=None,
    dialect_enforcement="off", transliteration_allowed=False,
    morphologically_productive=False, canonicalization="nfc",
    canonical_form_required=False, mode="advisory", post_call_contract=None,
)


def run(prompt: str, tool_name: str, city_arg: str, *, hallucinate: bool):
    """Push one request through the scale; return the combined receipt."""
    # 1+2) restore + balance
    result = preflight(
        prompt,
        PreflightContext(contradiction_predicates=[("احجز", "الغ")]),
    )
    receipt = result.receipt
    if not result.ok:
        return receipt  # fail-loud: contradiction, stop here

    tool_call = {"tool_name": tool_name, "args": {"city": city_arg}}

    # 3) classify / gate (qadiya)
    decision = GATE.check(tool_call)
    receipt = receipt.with_stage(decision.record)
    if not decision.allowed:
        return receipt  # escalate, never silently run

    # 4) constrain the Arabic argument (mtg)
    constrain_rec, _ = constrain(city_arg, CITY_SPEC)
    receipt = receipt.with_stage(constrain_rec)

    # 5) verify execution (toolproof): record the real call, then verify a
    #    claim. If hallucinate=True, the agent claims a call that never ran.
    store = tp.ReceiptStore()
    proxy = tp.ToolProxy(store, SECRET)
    proxy.record(tool_name, {"city": city_arg}, {"confirmation": "OK123"})
    verifier = tp.Verifier(store, SECRET)
    if hallucinate:
        claim = tp.AgentClaim("delete_db", {"target": "prod"}, {"ok": True})
    else:
        claim = tp.AgentClaim(tool_name, {"city": city_arg}, {"confirmation": "OK123"})
    vresult = verifier.verify_claim(claim)
    receipt = receipt.with_stage(record_from_toolproof(vresult))

    return receipt


def show(title: str, receipt) -> None:
    print(f"\n=== {title} ===")
    print(f"ok={receipt.ok}  blocked_by={list(receipt.blocked_by)}")
    for s in receipt.stages:
        flag = "ok " if s.ok else "BLOCK"
        print(f"  [{flag}] {s.stage:9} {s.tool}")
    print(receipt.to_json(indent=2)[:0] or "", end="")  # keep JSON available


def main() -> None:
    clean = run(
        "احجز رحلة إلى الرياض",
        tool_name="book_flight",
        city_arg="الرياض",
        hallucinate=False,
    )
    show("Clean Arabic request — survives every stage", clean)

    bad = run(
        "احجز رحلة إلى الرياض",
        tool_name="book_flight",
        city_arg="Riyadh",  # transliterated -> mtg fail
        hallucinate=True,    # claims a tool that never ran -> toolproof UNVERIFIED
    )
    show("Failure path — transliteration + hallucinated claim", bad)

    print("\nScale verdict:")
    print(f"  clean receipt ok       : {clean.ok}")
    print(f"  failure receipt ok     : {bad.ok}  (caught by: {list(bad.blocked_by)})")


if __name__ == "__main__":
    main()
