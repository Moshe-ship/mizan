"""Tests for the qadiya-backed ToolGate."""

from __future__ import annotations

import pytest

from mizan import (
    GateDecision,
    STAGE_CLASSIFY,
    ToolGate,
    equals_constraint,
    predicate_constraint,
)


def _in_repo(inp) -> bool:
    return str(inp.get("path", "")).startswith("/repo/")


def make_gate() -> ToolGate:
    # Two constraints: which tool, and whether the path is inside the repo.
    tool = equals_constraint("tool", "tool_name", ["read_file", "write_file"])
    scope = predicate_constraint("in_repo", _in_repo)
    # Allow: read anywhere in the listed tools that is in-repo; write in-repo.
    allowed = [
        "tool=read_file|in_repo=True",
        "tool=write_file|in_repo=True",
    ]
    return ToolGate([tool, scope], allowed)


def test_gate_enumerates_complete_case_space():
    gate = make_gate()
    # 3 tool values (read, write, __other__) x 2 in_repo = 6 cases.
    assert len(gate.cases) == 6


def test_allowed_tool_in_repo_passes():
    gate = make_gate()
    d = gate.check({"tool_name": "write_file", "path": "/repo/src/a.py"})
    assert isinstance(d, GateDecision)
    assert d.allowed is True
    assert d.record.ok is True
    assert d.record.stage == STAGE_CLASSIFY


def test_write_outside_repo_is_escalated():
    gate = make_gate()
    d = gate.check({"tool_name": "write_file", "path": "/etc/passwd"})
    assert d.allowed is False
    assert d.record.ok is False
    assert "escalated" in d.reason


def test_unknown_tool_routes_to_other_and_blocks():
    gate = make_gate()
    d = gate.check({"tool_name": "rm_rf_everything", "path": "/repo/x"})
    assert d.allowed is False
    assert "tool=__other__" in d.case_id


def test_missing_args_do_not_crash():
    gate = make_gate()
    d = gate.check({"tool_name": "read_file"})  # no path key
    # path absent -> in_repo False -> read_file|in_repo=False not allowed
    assert d.allowed is False


def test_bad_allowlist_entry_rejected_at_construction():
    tool = equals_constraint("tool", "tool_name", ["read_file"])
    with pytest.raises(ValueError):
        ToolGate([tool], ["tool=does_not_exist"])
