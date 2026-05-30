"""End-to-end pipeline test (skipped if mtg/toolproof are absent)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("mtg")
pytest.importorskip("toolproof")


def _load_demo():
    path = Path(__file__).resolve().parent.parent / "examples" / "end_to_end.py"
    spec = importlib.util.spec_from_file_location("mizan_end_to_end_demo", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_clean_request_survives_every_stage():
    demo = _load_demo()
    receipt = demo.run(
        "احجز رحلة إلى الرياض", tool_name="book_flight",
        city_arg="الرياض", hallucinate=False,
    )
    assert receipt.ok is True
    assert [s.stage for s in receipt.stages] == [
        "restore", "balance", "classify", "constrain", "verify",
    ]
    assert receipt.blocked_by == ()


def test_failure_path_is_caught_by_mtg_and_toolproof():
    demo = _load_demo()
    receipt = demo.run(
        "احجز رحلة إلى الرياض", tool_name="book_flight",
        city_arg="Riyadh", hallucinate=True,
    )
    assert receipt.ok is False
    assert set(receipt.blocked_by) == {"mtg", "toolproof"}


def test_unlisted_tool_is_escalated_before_constrain():
    demo = _load_demo()
    receipt = demo.run(
        "احذف كل شيء", tool_name="delete_everything",
        city_arg="الرياض", hallucinate=False,
    )
    # Gate escalates -> pipeline stops at classify, never reaches mtg/toolproof.
    assert receipt.ok is False
    assert [s.stage for s in receipt.stages][-1] == "classify"
