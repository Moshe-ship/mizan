"""Tests for the unified mizan preflight and receipt."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from mizan import (
    PreflightContext,
    Receipt,
    StageRecord,
    STAGE_BALANCE,
    STAGE_RESTORE,
    preflight,
    strip_tags,
)

NOW = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)


def test_clean_passthrough_is_ok():
    r = preflight("post the update", PreflightContext(now=NOW))
    assert r.ok is True
    assert r.contradiction is None
    assert r.receipt.ok is True
    # Two stages always run on a clean input.
    assert [s.stage for s in r.receipt.stages] == [STAGE_RESTORE, STAGE_BALANCE]


def test_restore_resolves_references_and_records_changes():
    r = preflight(
        "tell her tomorrow to post in <channel>",
        PreflightContext(
            now=NOW, referents={"her": "Alice"}, defaults={"channel": "#eng"}
        ),
    )
    assert r.ok is True
    restore_stage = r.receipt.stages[0]
    assert restore_stage.tool == "jabr"
    # her + tomorrow + <channel> -> at least 2 substitutions recorded.
    assert restore_stage.changes >= 2
    # The resolved date is carried in the trace detail.
    values = {e["value"] for e in restore_stage.detail.get("entries", [])}
    assert "Alice" in values
    assert "2026-05-31" in values  # tomorrow relative to NOW


def test_contradiction_is_fail_loud():
    r = preflight(
        "send it. cancel it.",
        PreflightContext(now=NOW, contradiction_predicates=[("send", "cancel")]),
    )
    assert r.ok is False
    assert r.contradiction is not None
    assert r.receipt.ok is False
    assert r.receipt.blocked_by == ("muqabalah",)


def test_clean_output_strips_jabr_tags():
    r = preflight(
        "tell her hello", PreflightContext(now=NOW, referents={"her": "Alice"})
    )
    assert "[[jabr:" in r.output  # annotated form keeps tags
    assert "[[jabr:" not in r.clean_output  # readable form does not


def test_original_is_recoverable_from_receipt():
    text = "tell her tomorrow"
    r = preflight(text, PreflightContext(now=NOW, referents={"her": "Alice"}))
    assert r.receipt.input == text


def test_receipt_is_json_serialisable():
    r = preflight("post in <channel>", PreflightContext(now=NOW, defaults={"channel": "#eng"}))
    js = r.receipt.to_json()
    assert isinstance(js, str)
    assert '"stages"' in js


def test_receipt_immutability_and_chaining():
    base = Receipt(input="x", output="x")
    rec = base.with_stage(StageRecord(stage="verify", tool="toolproof", ok=False))
    # base unchanged (immutable)
    assert base.stages == ()
    assert base.ok is True
    # new receipt carries the failing stage
    assert rec.ok is False
    assert rec.blocked_by == ("toolproof",)


def test_strip_tags_is_idempotent_on_plain_text():
    assert strip_tags("plain text") == "plain text"
