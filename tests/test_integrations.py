"""Tests for the mtg/toolproof -> Receipt adapters."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from mizan import record_from_mtg, record_from_toolproof
from mizan.receipt import STAGE_CONSTRAIN, STAGE_VERIFY


# --- fakes (decoupled from the real packages) ---------------------------- #


@dataclass
class _Viol:
    code: str
    severity: str
    phase: str = "pre"
    message: str = ""


class _GuardResult:
    def __init__(self, violations, repairs=(), repaired_surface=None):
        self.violations = violations
        self.repairs = repairs
        self.repaired_surface = repaired_surface


class _Verdict:
    def __init__(self, name):
        self.name = name


# --- mtg adapter --------------------------------------------------------- #


def test_mtg_clean_is_ok():
    rec = record_from_mtg(_GuardResult(violations=[]))
    assert rec.stage == STAGE_CONSTRAIN
    assert rec.tool == "mtg"
    assert rec.ok is True


def test_mtg_high_severity_fails():
    rec = record_from_mtg(_GuardResult(violations=[_Viol("SCRIPT_VIOLATION", "high")]))
    assert rec.ok is False
    assert rec.detail["violations"][0]["code"] == "SCRIPT_VIOLATION"


def test_mtg_low_severity_passes():
    rec = record_from_mtg(_GuardResult(violations=[_Viol("NOTE", "low")]))
    assert rec.ok is True


def test_mtg_counts_repairs_as_changes():
    rec = record_from_mtg(
        _GuardResult(violations=[], repairs=["r1", "r2"], repaired_surface="x")
    )
    assert rec.changes == 2
    assert rec.detail["repaired_surface"] == "x"


# --- toolproof adapter --------------------------------------------------- #


def test_toolproof_verified_is_ok():
    rec = record_from_toolproof(_Verdict("VERIFIED"))
    assert rec.stage == STAGE_VERIFY
    assert rec.tool == "toolproof"
    assert rec.ok is True
    assert rec.detail["verdict"] == "VERIFIED"


@pytest.mark.parametrize("name", ["UNVERIFIED", "TAMPERED"])
def test_toolproof_non_verified_is_not_ok(name):
    rec = record_from_toolproof(_Verdict(name))
    assert rec.ok is False
    assert rec.detail["verdict"] == name


def test_toolproof_accepts_result_with_verdict_attr():
    class _Result:
        verdict = _Verdict("VERIFIED")

    rec = record_from_toolproof(_Result())
    assert rec.ok is True


# --- real mtg (skipped if not installed) --------------------------------- #


def test_real_mtg_transliteration_fails_arabic_passes():
    mtg = pytest.importorskip("mtg")
    spec = mtg.GuardSpec(
        slot_type="city", script="ar", dialect_expected=None,
        dialect_enforcement="off", transliteration_allowed=False,
        morphologically_productive=False, canonicalization="nfc",
        canonical_form_required=False, mode="advisory", post_call_contract=None,
    )
    from mizan import constrain
    rec_ar, _ = constrain("الرياض", spec)
    rec_latin, _ = constrain("Riyadh", spec)
    assert rec_ar.ok is True
    assert rec_latin.ok is False
