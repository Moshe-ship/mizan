"""`mizan report` — renders a self-contained HTML report from a receipt log."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mizan.chain import ReceiptLog
from mizan.receipt import Receipt, StageRecord
from mizan.report import render_html


def _log(tmp_path) -> str:
    path = os.path.join(tmp_path, "receipts.jsonl")
    log = ReceiptLog(path)
    allow = Receipt("search(q)", "allowed",
                    stages=(StageRecord(stage="classify", tool="qadiya", ok=True),))
    block = Receipt("terminal(ls)", "blocked",
                    stages=(StageRecord(stage="classify", tool="qadiya", ok=False,
                                        detail={"reason": "not in allowlist"}),))
    log.append(allow.to_v0(secret="s", run_id="sess1", tool="search"))
    log.append(block.to_v0(secret="s", run_id="sess1", tool="terminal"))
    return path


def test_report_renders_signed_chain(tmp_path):
    path = _log(str(tmp_path))
    html = render_html(path, secret="s")
    assert "Mizan" in html and "chain intact" in html
    assert "VALID" in html               # signatures checked with the right secret
    assert "allowed" in html and "blocked" in html
    assert "terminal" in html and "sess1" in html


def test_report_flags_tamper(tmp_path):
    path = _log(str(tmp_path))
    # corrupt the last receipt's body in place
    lines = open(path).read().splitlines()
    import json
    obj = json.loads(lines[-1])
    obj["receipt"]["decision"]["action"] = "allowed"   # lie
    lines[-1] = json.dumps(obj)
    open(path, "w").write("\n".join(lines) + "\n")
    html = render_html(path, secret="s")
    # the signature no longer matches -> TAMPERED, and the chain digest breaks
    assert "TAMPERED" in html
    assert "chain BROKEN" in html


def test_report_without_secret_shows_unchecked(tmp_path):
    path = _log(str(tmp_path))
    html = render_html(path)               # no secret
    assert "signed (no key)" in html       # signed but not verified
    assert "not checked" in html


if __name__ == "__main__":
    import tempfile
    for fn in (test_report_renders_signed_chain, test_report_flags_tamper,
               test_report_without_secret_shows_unchecked):
        fn(tempfile.mkdtemp())
        print("OK:", fn.__name__)
    print("\nALL PASS")
