"""Hash-chained append-only receipt log: sequence tamper-evidence."""

from __future__ import annotations

import json
import types

from mizan import chain, receipt_v0
from mizan.chain import GENESIS, ReceiptLog, verify_log
from mizan.receipt import Receipt
from mizan.verify import cmd_verify_log

SECRET = "log-secret"


def _build(path, n=4):
    log = ReceiptLog(str(path))
    for i in range(n):
        log.append(Receipt(f"req-{i}", "ok").to_v0(secret=SECRET, receipt_id=f"rcpt_{i}"))
    return log


def test_append_and_verify_intact(tmp_path):
    p = tmp_path / "audit.jsonl"
    log = _build(p, 4)
    assert len(log) == 4
    assert log.head_digest() != GENESIS
    ok, problems = verify_log(str(p))
    assert ok and problems == []


def test_first_link_anchors_to_genesis(tmp_path):
    p = tmp_path / "a.jsonl"
    _build(p, 1)
    first = json.loads(p.read_text().splitlines()[0])
    assert first["prev"] == GENESIS
    assert first["digest"] == chain.link_digest(GENESIS, first["receipt"])


def _rewrite(p, lines):
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def test_tampered_receipt_breaks_chain(tmp_path):
    p = tmp_path / "a.jsonl"
    _build(p, 4)
    lines = [json.loads(l) for l in p.read_text().splitlines()]
    lines[1]["receipt"]["output"]["hash"] = "sha256:" + "0" * 64
    _rewrite(p, lines)
    ok, problems = verify_log(str(p))
    assert not ok and any("digest mismatch" in s for s in problems)


def test_removed_entry_breaks_chain(tmp_path):
    p = tmp_path / "a.jsonl"
    _build(p, 4)
    lines = [json.loads(l) for l in p.read_text().splitlines()]
    del lines[2]
    _rewrite(p, lines)
    assert verify_log(str(p))[0] is False


def test_reordered_entries_break_chain(tmp_path):
    p = tmp_path / "a.jsonl"
    _build(p, 4)
    lines = [json.loads(l) for l in p.read_text().splitlines()]
    lines[1], lines[2] = lines[2], lines[1]
    _rewrite(p, lines)
    assert verify_log(str(p))[0] is False


def test_tail_truncation_needs_an_anchor(tmp_path):
    p = tmp_path / "a.jsonl"
    log = _build(p, 4)
    head, count = log.head_digest(), len(log)
    # drop the last entry — the remaining prefix is a valid chain from genesis
    lines = [json.loads(l) for l in p.read_text().splitlines()][:-1]
    _rewrite(p, lines)
    assert verify_log(str(p))[0] is True                         # bare: undetectable
    assert verify_log(str(p), expect_count=count)[0] is False    # anchor catches it
    assert verify_log(str(p), expect_head=head)[0] is False


def _args(log, secret_env="MIZAN_RECEIPT_SECRET", public_key=None,
          expect_head=None, expect_count=None):
    return types.SimpleNamespace(log=str(log), secret_env=secret_env, public_key=public_key,
                                 expect_head=expect_head, expect_count=expect_count)


def test_cli_anchor_detects_tail_truncation(tmp_path, monkeypatch):
    p = tmp_path / "a.jsonl"
    log = _build(p, 4)
    count = len(log)
    monkeypatch.delenv("MIZAN_RECEIPT_SECRET", raising=False)
    lines = [json.loads(l) for l in p.read_text().splitlines()][:-1]
    _rewrite(p, lines)
    assert cmd_verify_log(_args(p)) == 0                      # bare CLI: passes
    assert cmd_verify_log(_args(p, expect_count=count)) == 1  # anchored: fails


def test_cli_chain_only_and_with_signatures(tmp_path, monkeypatch):
    p = tmp_path / "a.jsonl"
    _build(p, 3)
    monkeypatch.delenv("MIZAN_RECEIPT_SECRET", raising=False)
    assert cmd_verify_log(_args(p)) == 0  # chain only (no key provided)
    monkeypatch.setenv("MIZAN_RECEIPT_SECRET", SECRET)
    assert cmd_verify_log(_args(p)) == 0  # chain + valid signatures


def test_cli_wrong_secret_is_exit_2(tmp_path, monkeypatch):
    p = tmp_path / "a.jsonl"
    _build(p, 3)
    monkeypatch.setenv("MIZAN_RECEIPT_SECRET", "wrong")
    assert cmd_verify_log(_args(p)) == 2  # chain intact, signatures fail


def test_cli_broken_chain_is_exit_1(tmp_path):
    p = tmp_path / "a.jsonl"
    _build(p, 3)
    lines = [json.loads(l) for l in p.read_text().splitlines()]
    lines[0]["receipt"]["output"]["hash"] = "sha256:" + "f" * 64
    _rewrite(p, lines)
    assert cmd_verify_log(_args(p)) == 1
