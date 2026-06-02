"""Append-only, hash-chained receipt log — tamper-evidence for the *sequence*.

A signature proves each receipt is intact. A hash chain proves the **log** was
not reordered, truncated, or had entries inserted: each link commits to the
previous link's digest, so any edit breaks the chain from that point on.

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
from typing import Any

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


def verify_log(path: str) -> tuple[bool, list[str]]:
    """Verify the chain is unbroken from genesis. Returns (ok, problems).

    Detects per-link receipt tampering, a broken/forged `prev` link, a removed
    or reordered entry (via `seq` and link recomputation), and insertion.
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
    return (not problems, problems)
