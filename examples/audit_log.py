"""An append-only, hash-chained audit trail — and what tampering looks like.

Per-receipt signatures prove each receipt is intact; the hash chain proves the
log sequence wasn't reordered or had entries removed. Runs on a bare install.

    python examples/audit_log.py
    mizan verify-log /tmp/mizan-audit.jsonl --secret-env MIZAN_RECEIPT_SECRET
"""

from __future__ import annotations

import json
import os

from mizan.chain import ReceiptLog, verify_log
from mizan.receipt import Receipt

SECRET = "demo-secret"
PATH = "/tmp/mizan-audit.jsonl"


def main() -> None:
    if os.path.exists(PATH):
        os.remove(PATH)

    log = ReceiptLog(PATH)
    for i in range(4):
        log.append(Receipt(f"request-{i}", "ok").to_v0(secret=SECRET, receipt_id=f"rcpt_{i}"))
    print(f"appended {len(log)} signed receipts to {PATH}")
    print(f"  head digest: {log.head_digest()[:24]}…")
    ok, _ = verify_log(PATH)
    print(f"  chain intact: {ok}")

    # An attacker with write access deletes the second receipt to hide an action.
    lines = [json.loads(l) for l in open(PATH, encoding="utf-8")]
    del lines[1]
    with open(PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(json.dumps(x) for x in lines) + "\n")

    ok, problems = verify_log(PATH)
    print(f"\nafter deleting receipt #1: chain intact = {ok}")
    for p in problems[:3]:
        print(f"  - {p}")
    print(f"\n  reproduce: MIZAN_RECEIPT_SECRET={SECRET} mizan verify-log {PATH}")


if __name__ == "__main__":
    main()
