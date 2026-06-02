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
from typing import Any, Optional

from mizan import receipt_v0


def _load(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _read_public_key(path: Optional[str]) -> Optional[str]:
    """Read an Ed25519 public key: a keygen JSON ({"public_key": hex}) or raw hex."""
    if not path:
        return None
    text = open(path, "r", encoding="utf-8").read().strip()
    try:
        obj = json.loads(text)
        return obj.get("public_key") if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return text  # raw hex


def cmd_keygen(args: Any) -> int:
    from mizan.signing import Ed25519Signer

    try:
        signer = Ed25519Signer.generate(key_id=getattr(args, "key_id", None))
    except ImportError as exc:
        print(f"✗ {exc}")
        return 1
    keypair = {
        "algorithm": "Ed25519",
        "key_id": signer.key_id,
        "public_key": signer.public_key_hex(),
        "private_key": signer.private_key_hex(),
    }
    out = getattr(args, "out", None)
    if out:
        import os
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(keypair, fh, indent=2)
        os.chmod(out, 0o600)
        print(f"wrote keypair to {out} (mode 600). Keep `private_key` secret; "
              f"distribute only `public_key`.")
    else:
        print(json.dumps(keypair, indent=2))
        print("# Keep private_key secret; share only public_key for `mizan verify --public-key`.")
    return 0


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

    algorithm = (receipt.get("signature") or {}).get("algorithm")
    secret = os.environ.get(args.secret_env)
    public_key = _read_public_key(getattr(args, "public_key", None))
    value = (receipt.get("signature") or {}).get("value")

    if not value:
        status = receipt_v0.UNSIGNED
    else:
        # dispatch on the receipt's own algorithm
        try:
            status = receipt_v0.verify(receipt, secret, public_key=public_key)
        except ImportError as exc:  # Ed25519 receipt on a bare install
            print(f"✗ {receipt.get('receipt_id', '?')}: {exc}")
            return 1

    rid = receipt.get("receipt_id", "?")
    decision = receipt.get("decision", {}).get("action", "?")
    verif = receipt.get("verification", "?")

    if status == receipt_v0.OK:
        # Signature holds. Now weigh the agent's claim against observed execution.
        # The RECOMPUTED comparison is authoritative — never the receipt's own
        # `verification` field, which a signer could under- or over-state.
        execution, claim = receipt.get("execution"), receipt.get("claim")
        if execution and claim:
            recomputed = receipt_v0.attest_claim(execution, claim)
            if verif == "verified" and recomputed != "verified":
                # the receipt over-claims a positive verdict
                print(f"✗ {rid}: DISHONEST — receipt declares verification 'verified' but the "
                      f"claim does not match execution (recomputed: {recomputed})")
                return receipt_v0.status_exit_code(receipt_v0.INVALID)
            if recomputed == "tampered":
                # the claim genuinely does not match execution — regardless of
                # what the receipt's own verification field says.
                print(f"✗ {rid}: signature VALID, but the agent's CLAIM does NOT match execution "
                      f"— the agent lied about the result (claim mismatch)")
                if getattr(args, "allow_claim_mismatch", False):
                    print("  accepted (--allow-claim-mismatch)")
                    return 0
                return receipt_v0.status_exit_code(receipt_v0.CLAIM_MISMATCH)
            print(f"✓ {rid}: signature VALID · decision={decision} · claim={recomputed}")
            return 0
        print(f"✓ {rid}: signature VALID · decision={decision} · verification={verif}")
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
    # NO_SECRET — no key for the receipt's algorithm
    if algorithm == "Ed25519":
        print(f"⚠ {rid}: Ed25519-signed, but no public key to check it. "
              f"Pass --public-key <file> to verify.")
    else:
        print(f"⚠ {rid}: signed, but no secret to check it. "
              f"Set ${args.secret_env} to verify the signature.")
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


def cmd_verify_log(args: Any) -> int:
    """Verify a hash-chained receipt log: sequence integrity, and optionally
    each receipt's signature. Exit: 0 ok · 1 chain broken · 2 a signature failed."""
    from mizan import chain

    ok, problems = chain.verify_log(
        args.log,
        expect_head=getattr(args, "expect_head", None),
        expect_count=getattr(args, "expect_count", None),
    )
    try:
        with open(args.log, "r", encoding="utf-8") as fh:
            links = [json.loads(l) for l in fh if l.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        print(f"✗ cannot read log: {exc}")
        return 1

    if not ok:
        print(f"✗ chain check FAILED ({len(problems)} problem(s)):")
        for p in problems[:20]:
            print(f"    - {p}")
        return 1
    anchored = getattr(args, "expect_head", None) or getattr(args, "expect_count", None)
    head = links[-1]["digest"] if links else chain.GENESIS
    print(f"✓ chain intact: {len(links)} link(s), unbroken from genesis"
          + (" + matches anchor" if anchored else ""))
    if not anchored:
        print(f"  head digest (anchor this to detect tail truncation): {head}")

    secret = os.environ.get(args.secret_env)
    public_key = _read_public_key(getattr(args, "public_key", None))
    if secret is None and public_key is None:
        return 0  # chain-only check requested

    bad = []
    for rec in links:
        try:
            status = receipt_v0.verify(rec.get("receipt", {}), secret, public_key=public_key)
        except ImportError as exc:
            print(f"✗ {exc}")
            return 1
        if status != receipt_v0.OK:
            bad.append((rec.get("seq"), status))
    if bad:
        print(f"✗ {len(bad)} receipt signature(s) not OK: {bad[:10]}")
        return 2
    print(f"✓ all {len(links)} receipt signatures valid")
    return 0
