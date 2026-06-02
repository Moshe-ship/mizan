"""`mizan verify` and `mizan diff` — check and compare signed receipts.

Dependency-free: structural validation + HMAC signature checking work on a bare
`pip install mizan`. Full JSON-Schema validation runs additionally if
`jsonschema` is installed.

Exit codes (verify): 0 ok · 1 invalid/schema · 2 tampered (signature) ·
3 unsigned · 4 no-secret · 5 claim-mismatch (agent claim != execution).
"""

from __future__ import annotations

import json
import os
from typing import Any

from mizan import receipt_v0


def _load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def cmd_verify(args: Any) -> int:
    try:
        receipt = _load(args.receipt)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"✗ cannot read receipt: {exc}")
        return receipt_v0.status_exit_code(receipt_v0.INVALID)

    errors = receipt_v0.structural_errors(receipt)
    full = receipt_v0.full_validation_errors(receipt)
    if full:
        errors = errors + [f"schema: {m}" for m in full]
    if errors:
        print("✗ invalid receipt:")
        for e in errors[:10]:
            print(f"    - {e}")
        return receipt_v0.status_exit_code(receipt_v0.INVALID)

    secret = os.environ.get(args.secret_env)
    value = (receipt.get("signature") or {}).get("value")

    if not value:
        status = receipt_v0.UNSIGNED
    elif secret is None:
        status = receipt_v0.NO_SECRET
    else:
        status = receipt_v0.verify(receipt, secret)

    rid = receipt.get("receipt_id", "?")
    decision = receipt.get("decision", {}).get("action", "?")
    verif = receipt.get("verification", "?")

    if status == receipt_v0.OK:
        # Signature holds. Now: does the agent's claim match observed execution?
        execution, claim = receipt.get("execution"), receipt.get("claim")
        if execution and claim:
            recomputed = receipt_v0.attest_claim(execution, claim)
            if verif == "verified" and recomputed != "verified":
                # signed receipt asserts "verified" but the hashes disagree
                print(f"✗ {rid}: DISHONEST — verification says 'verified' but the claim "
                      f"does not match execution ({recomputed})")
                return receipt_v0.status_exit_code(receipt_v0.INVALID)
        if verif == "tampered":
            print(f"✗ {rid}: signature VALID, but the agent's CLAIM does NOT match execution "
                  f"— the agent lied about the result (claim mismatch)")
            if getattr(args, "allow_claim_mismatch", False):
                print("  accepted (--allow-claim-mismatch)")
                return 0
            return receipt_v0.status_exit_code(receipt_v0.CLAIM_MISMATCH)
        print(f"✓ {rid}: signature VALID · decision={decision} · claim={verif}")
        return 0
    if status == receipt_v0.TAMPERED:
        print(f"✗ {rid}: signature MISMATCH — receipt was modified after signing (TAMPERED)")
        return receipt_v0.status_exit_code(status)
    if status == receipt_v0.UNSIGNED:
        msg = f"⚠ {rid}: structurally valid but UNSIGNED (signature.value is null)"
        if getattr(args, "allow_unsigned", False):
            print(msg + " — accepted (--allow-unsigned)")
            return 0
        print(msg)
        return receipt_v0.status_exit_code(status)
    # NO_SECRET
    print(
        f"⚠ {rid}: signed, but no secret to check it. "
        f"Set ${args.secret_env} to verify the signature."
    )
    return receipt_v0.status_exit_code(receipt_v0.NO_SECRET)


# Fields excluded from `diff` unless --include-volatile (they change every run).
_VOLATILE = ("receipt_id", "created_at", "signature")


def _semantic(receipt: dict, include_volatile: bool) -> dict:
    if include_volatile:
        return receipt
    return {k: v for k, v in receipt.items() if k not in _VOLATILE}


def _diff(a: Any, b: Any, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            out += _diff(a.get(k, "∅"), b.get(k, "∅"), f"{path}.{k}" if path else k)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"  {path}: list length {len(a)} → {len(b)}")
        for i in range(min(len(a), len(b))):
            out += _diff(a[i], b[i], f"{path}[{i}]")
    elif a != b:
        out.append(f"  {path}: {a!r} → {b!r}")
    return out


def cmd_diff(args: Any) -> int:
    try:
        a, b = _load(args.a), _load(args.b)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"✗ cannot read receipts: {exc}")
        return 1
    inc = getattr(args, "include_volatile", False)
    diffs = _diff(_semantic(a, inc), _semantic(b, inc))
    if not diffs:
        scope = "including volatile fields" if inc else "ignoring receipt_id/created_at/signature"
        print(f"✓ receipts are equivalent ({scope})")
        return 0
    print(f"✗ {len(diffs)} difference(s):")
    for line in diffs[:40]:
        print(line)
    return 1
