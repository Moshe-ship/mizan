"""Deterministic generator for the example receipts in examples/receipts/.

These are FIXTURES, not hand-maintained samples: they are produced from
`Receipt.to_v0()` with fixed ids/timestamps/secret. `test_receipt_v0.py`
re-runs `build()` and asserts the committed files still match (drift guard).

Regenerate the committed files intentionally with:

    python tests/fixtures_gen.py
"""

from __future__ import annotations

import json
import pathlib

from mizan import receipt_v0
from mizan.receipt import Receipt, StageRecord

SECRET = "demo-secret-do-not-use-in-prod"
KEY_ID = "demo"

_ARGS_HASH = receipt_v0.hash_text('{"from":"RUH","to":"JED"}')
_RESULT_HASH = receipt_v0.hash_text("PNR:ABC123")


def _passed() -> dict:
    r = Receipt(
        input="احجز رحلة من الرياض إلى جدة",
        output="booking confirmed",
        stages=(
            StageRecord("scan", "mcpscan", True, 0, {"findings": 0}),
            StageRecord("restore", "jabr", True, 1, {"spans_restored": 1}),
            StageRecord("balance", "muqabalah", True, 0, {}),
            StageRecord("classify", "qadiya", True, 0, {"case": "book_flight"}),
            StageRecord("constrain", "mtg", True, 0, {"violations": 0}),
            StageRecord("verify", "toolproof", True, 0, {
                "verdict": "VERIFIED",
                "execution": {
                    "tool": "book_flight", "args_hash": _ARGS_HASH,
                    "result_hash": _RESULT_HASH, "observed_status": "ok",
                },
                "claim": {"tool": "book_flight", "result_hash": _RESULT_HASH},
            }),
        ),
    )
    return r.to_v0(
        secret=SECRET, key_id=KEY_ID, redact=False,
        agent_id="agent-demo", model="claude-opus-4-8", run_id="run-001",
        receipt_id="rcpt_5f0c1a2b", created_at="2026-06-01T18:30:00Z",
    )


def _blocked() -> dict:
    r = Receipt(
        input="use the get_weather tool",
        output="",
        stages=(
            StageRecord("scan", "mcpscan", False, 0, {
                "findings": 1, "rule": "R-BIDI-001", "severity": "high"}),
        ),
    )
    return r.to_v0(
        secret=SECRET, key_id=KEY_ID, redact=True,
        agent_id="agent-demo", model="claude-opus-4-8", run_id="run-002",
        receipt_id="rcpt_77a3e910", created_at="2026-06-01T18:31:00Z",
    )


def _tampered() -> dict:
    # A correctly-signed receipt, then mutated AFTER signing → signature invalid.
    doc = _passed()
    doc["receipt_id"] = "rcpt_dead0000"
    doc["created_at"] = "2026-06-01T18:32:00Z"
    doc["signature"]["value"] = receipt_v0.sign(doc, SECRET)  # re-sign for the new id/time
    doc["execution"]["result_hash"] = receipt_v0.hash_text("PNR:EVIL999")  # tamper after signing
    return doc


def build() -> dict[str, dict]:
    return {"passed": _passed(), "blocked": _blocked(), "tampered": _tampered()}


def _dir() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent / "examples" / "receipts"


def write() -> None:
    out = _dir()
    out.mkdir(parents=True, exist_ok=True)
    for name, doc in build().items():
        (out / f"{name}.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {out / (name + '.json')}")


if __name__ == "__main__":
    write()
