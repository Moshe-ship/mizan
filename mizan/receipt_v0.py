"""Mizan Receipt v0 — the signed evidence object.

This module turns a :class:`mizan.receipt.Receipt` into the portable, signed
v0 document defined in ``docs/RECEIPT_SPEC.md`` and validated by
``mizan/schemas/receipt-v0.schema.json``.

It is **additive**: ``Receipt.to_dict()`` is unchanged. ``Receipt.to_v0()``
(and the helpers here) are opt-in. Everything is pure-Python and dependency
free — the scanner-only install can verify receipts.

Canonicalization (for signing) is RFC 8785 (JCS) aligned, constrained to the
receipt value space: objects, arrays, strings, integers, booleans, null —
**no floats** (a float raises, so signers and verifiers can never disagree on
number formatting). Keys are ASCII in v0, so code-point and UTF-16 ordering
coincide.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Sequence

SCHEMA_VERSION = "mizan.receipt/0"
SIGNATURE_ALGORITHM = "HMAC-SHA256"

# mizan verify exit statuses
OK = "ok"
INVALID = "invalid"            # structural/schema failure
TAMPERED = "tampered"          # signature present but does not match
UNSIGNED = "unsigned"          # signature value is null
NO_SECRET = "no_secret"        # signed receipt but no secret provided to check

_STATUS_EXIT = {OK: 0, INVALID: 1, TAMPERED: 2, UNSIGNED: 3, NO_SECRET: 4}


def status_exit_code(status: str) -> int:
    return _STATUS_EXIT.get(status, 1)


# --------------------------------------------------------------------------- #
# Canonicalization & signing
# --------------------------------------------------------------------------- #
def _reject_floats(obj: Any) -> None:
    if isinstance(obj, float):
        raise ValueError(
            "Receipt canonical form forbids floats (ambiguous across languages); "
            "use integers or strings."
        )
    if isinstance(obj, Mapping):
        for v in obj.values():
            _reject_floats(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _reject_floats(v)


def canonicalize(obj: Any) -> bytes:
    """RFC 8785-aligned canonical bytes for the receipt value space."""
    _reject_floats(obj)
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _body_for_signing(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in receipt.items() if k != "signature"}


def sign(receipt: Mapping[str, Any], secret: str) -> str:
    """HMAC-SHA256 hex over the canonical receipt with ``signature`` removed."""
    body = _body_for_signing(receipt)
    return hmac.new(secret.encode("utf-8"), canonicalize(body), hashlib.sha256).hexdigest()


def verify(receipt: Mapping[str, Any], secret: str) -> str:
    """Return a status: OK / TAMPERED / UNSIGNED."""
    value = (receipt.get("signature") or {}).get("value")
    if not value:
        return UNSIGNED
    expected = sign(receipt, secret)
    return OK if hmac.compare_digest(expected, str(value)) else TAMPERED


def hash_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _summary(text: str, redact: bool, cap: int = 200) -> Optional[str]:
    if redact:
        return None
    return text if len(text) <= cap else text[: cap - 1] + "…"


# --------------------------------------------------------------------------- #
# Projection: Receipt -> v0 document
# --------------------------------------------------------------------------- #
def _derive_decision(stages: Sequence[Any]) -> dict[str, str]:
    blocking = [s for s in stages if not s.ok]
    if blocking:
        b = blocking[0]
        return {"action": "blocked", "reason": f"{b.stage}:{b.tool} refused"}
    escalated = [
        s for s in stages
        if s.stage in ("classify", "constrain") and dict(s.detail).get("escalated")
    ]
    if escalated:
        e = escalated[0]
        return {"action": "escalated", "reason": f"{e.stage}:{e.tool} escalated for review"}
    return {"action": "allowed", "reason": "no stage refused"}


_VERDICT_MAP = {"VERIFIED": "verified", "UNVERIFIED": "unverified", "TAMPERED": "tampered"}


def project(
    receipt: Any,
    *,
    secret: Optional[str] = None,
    key_id: Optional[str] = None,
    redact: bool = True,
    agent_id: Optional[str] = None,
    model: Optional[str] = None,
    run_id: Optional[str] = None,
    tool: Optional[str] = None,
    receipt_id: Optional[str] = None,
    created_at: Optional[str] = None,
    execution: Optional[Mapping[str, Any]] = None,
    claim: Optional[Mapping[str, Any]] = None,
    verification: Optional[str] = None,
) -> dict[str, Any]:
    """Build a v0 receipt dict from a :class:`mizan.receipt.Receipt`.

    Signs it when ``secret`` is given; otherwise emits an unsigned draft
    (``signature.value = null``). Explicit ``execution``/``claim``/
    ``verification`` override the values derived from the verify stage.
    """
    stages = list(receipt.stages)

    verify_stage = next((s for s in stages if s.stage == "verify"), None)
    vdetail = dict(verify_stage.detail) if verify_stage is not None else {}

    if verification is None:
        if verify_stage is None:
            verification = "not_applicable"
        else:
            verification = _VERDICT_MAP.get(str(vdetail.get("verdict", "")).upper(), "unverified")
    if execution is None:
        execution = vdetail.get("execution")
    if claim is None:
        claim = vdetail.get("claim")

    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": receipt_id or ("rcpt_" + uuid.uuid4().hex[:12]),
        "created_at": created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "subject": {"agent_id": agent_id, "model": model, "run_id": run_id, "tool": tool},
        "input": {"hash": hash_text(receipt.input), "summary": _summary(receipt.input, redact)},
        "output": {"hash": hash_text(receipt.output), "summary": _summary(receipt.output, redact)},
        "decision": _derive_decision(stages),
        "execution": dict(execution) if execution is not None else None,
        "claim": dict(claim) if claim is not None else None,
        "verification": verification,
        "stages": [s.to_dict() for s in stages],
        "signature": {"algorithm": SIGNATURE_ALGORITHM, "key_id": key_id, "value": None},
    }
    if secret is not None:
        doc["signature"]["value"] = sign(doc, secret)
    return doc


# --------------------------------------------------------------------------- #
# Validation (pure-Python; full JSON-Schema if jsonschema is installed)
# --------------------------------------------------------------------------- #
def load_schema() -> Optional[dict[str, Any]]:
    try:
        from importlib import resources

        text = (resources.files("mizan") / "schemas" / "receipt-v0.schema.json").read_text(
            encoding="utf-8"
        )
        return json.loads(text)
    except Exception:
        return None


_REQUIRED = (
    "schema_version", "receipt_id", "created_at", "subject", "input", "output",
    "decision", "execution", "claim", "verification", "stages", "signature",
)
_STAGES = {"scan", "restore", "balance", "classify", "constrain", "verify"}
_ACTIONS = {"allowed", "blocked", "escalated"}
_VERIF = {"verified", "unverified", "tampered", "not_applicable"}


def structural_errors(receipt: Any) -> list[str]:
    """Dependency-free structural check. Returns a list of error strings."""
    errs: list[str] = []
    if not isinstance(receipt, dict):
        return ["receipt is not a JSON object"]
    for k in _REQUIRED:
        if k not in receipt:
            errs.append(f"missing required field: {k}")
    if receipt.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"schema_version must be {SCHEMA_VERSION!r}")
    if receipt.get("decision", {}).get("action") not in _ACTIONS:
        errs.append("decision.action invalid")
    if receipt.get("verification") not in _VERIF:
        errs.append("verification invalid")
    sig = receipt.get("signature")
    if not isinstance(sig, dict) or sig.get("algorithm") != SIGNATURE_ALGORITHM:
        errs.append("signature.algorithm must be HMAC-SHA256")
    else:
        val = sig.get("value")
        if val is not None and not (isinstance(val, str) and len(val) == 64):
            errs.append("signature.value must be 64-hex or null")
    for i, s in enumerate(receipt.get("stages", []) or []):
        if not isinstance(s, dict) or s.get("stage") not in _STAGES:
            errs.append(f"stages[{i}].stage invalid")
    return errs


def full_validation_errors(receipt: Any) -> Optional[list[str]]:
    """Full JSON-Schema validation if jsonschema is available, else None."""
    schema = load_schema()
    if schema is None:
        return None
    try:
        import jsonschema
    except Exception:
        return None
    v = jsonschema.Draft202012Validator(schema)
    return [e.message for e in sorted(v.iter_errors(receipt), key=lambda e: list(e.path))]
