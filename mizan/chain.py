"""Append-only, hash-chained receipt log — tamper-evidence for the *sequence*.

A signature proves each receipt is intact. A hash chain makes the **log**
tamper-evident: edits, insertions, reorders, and **middle** removals break the
chain, because each link commits to the previous link's digest.

One thing a bare chain cannot see on its own: **tail truncation**. Dropping the
most recent entries leaves a still-valid prefix from genesis, so it verifies as
intact. To detect it you must compare against an **external anchor** — pass
``expect_head`` (the head digest you recorded elsewhere) and/or ``expect_count``
to :func:`verify_log`, and/or store the log on write-once media.

    log = ReceiptLog("audit.jsonl")
    log.append(receipt_a)
    log.append(receipt_b)
    ok, problems = verify_log("audit.jsonl")

The log is plain JSONL — one link per line, append-only — so it ships straight
to a SIEM or object store. See docs/AUDIT_STORAGE.md. Dependency-free.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from mizan.receipt_v0 import canonicalize

#: The chain root. The first link's `prev` is the genesis digest.
GENESIS = "0" * 64


def link_digest(prev_hex: str, receipt: Any) -> str:
    """`sha256(prev_digest || canonical(receipt))` — binds a receipt to the prior link."""
    h = hashlib.sha256()
    h.update(bytes.fromhex(prev_hex))
    h.update(canonicalize(receipt))
    return h.hexdigest()


class ReceiptLog:
    """Append-only hash-chained log over a JSONL file.

    Each line is ``{"seq", "prev", "digest", "receipt"}``. Appends are O(file)
    today (they read to find the head); fine for audit volumes, and the format
    is what matters — a consumer can stream it without this class.
    """

    def __init__(self, path: str) -> None:
        self.path = path

    def _lines(self) -> list[dict]:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return [json.loads(l) for l in fh if l.strip()]
        except FileNotFoundError:
            return []

    def head_digest(self) -> str:
        lines = self._lines()
        return lines[-1]["digest"] if lines else GENESIS

    def __len__(self) -> int:
        return len(self._lines())

    def append(self, receipt: Any) -> dict:
        """Append a receipt as the next link; returns the link record."""
        lines = self._lines()
        prev = lines[-1]["digest"] if lines else GENESIS
        record = {
            "seq": len(lines),
            "prev": prev,
            "digest": link_digest(prev, receipt),
            "receipt": receipt,
        }
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record


def verify_log(
    path: str,
    *,
    expect_head: Optional[str] = None,
    expect_count: Optional[int] = None,
) -> tuple[bool, list[str]]:
    """Verify the chain is unbroken from genesis. Returns (ok, problems).

    Detects per-link receipt tampering, a broken/forged `prev` link, a removed
    or reordered **middle** entry, and insertion. **Tail truncation** is only
    detectable against an external anchor: pass ``expect_head`` (the head digest
    recorded elsewhere) and/or ``expect_count`` (the expected number of links).
    Signature verification is separate — pass each link's `receipt` to
    ``mizan.receipt_v0.verify``.
    """
    problems: list[str] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = [json.loads(l) for l in fh if l.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"cannot read log: {exc}"]

    expected_prev = GENESIS
    for i, rec in enumerate(lines):
        if rec.get("seq") != i:
            problems.append(f"line {i}: seq is {rec.get('seq')} (expected {i}) — entry removed or reordered")
        if rec.get("prev") != expected_prev:
            problems.append(f"line {i}: prev link broken — reorder/removal/insert")
        correct = link_digest(expected_prev, rec.get("receipt"))
        if rec.get("digest") != correct:
            problems.append(f"line {i}: digest mismatch — receipt or link tampered")
        expected_prev = correct  # anchor on the genesis-rooted correct chain

    # Anchored checks — the only way to catch tail truncation/extension.
    if expect_count is not None and len(lines) != expect_count:
        problems.append(
            f"log has {len(lines)} link(s), expected {expect_count} — tail truncated or extended"
        )
    if expect_head is not None and expected_prev != expect_head:
        problems.append(
            f"head digest {expected_prev[:12]}… != anchored {str(expect_head)[:12]}… "
            f"— tail truncated or altered"
        )
    return (not problems, problems)
