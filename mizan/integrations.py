"""Adapters that fold mtg and toolproof results into the shared Receipt.

The back half of the scale lives in separate packages (`mtg` for argument
constraint, `toolproof` for execution verification). These adapters convert
their native results into :class:`~mizan.receipt.StageRecord` so a single
agent turn produces one weighable trail across all stages.

The adapters accept *native result objects*, so `mizan` does not hard-depend
on `mtg`/`toolproof` being installed. The `constrain`/`verify` convenience
wrappers import them lazily.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from mizan.receipt import StageRecord, STAGE_CONSTRAIN, STAGE_VERIFY

# mtg severity -> outcome (mirrors mtg.SEVERITY_TO_OUTCOME; used as fallback).
_DEFAULT_SEVERITY_OUTCOME = {"high": "fail", "medium": "partial", "low": "pass", "info": "pass"}


def record_from_mtg(
    result: Any, severity_to_outcome: Optional[Mapping[str, str]] = None
) -> StageRecord:
    """Convert an ``mtg.GuardResult`` into a CONSTRAIN stage record.

    ``ok`` is False when any violation's severity maps to the ``fail``
    outcome. Repairs are counted as changes.
    """
    sev_map = severity_to_outcome or _DEFAULT_SEVERITY_OUTCOME
    violations = list(getattr(result, "violations", ()) or ())
    repairs = list(getattr(result, "repairs", ()) or ())
    fails = [
        v
        for v in violations
        if sev_map.get(str(getattr(v, "severity", "")).lower()) == "fail"
    ]
    return StageRecord(
        stage=STAGE_CONSTRAIN,
        tool="mtg",
        ok=len(fails) == 0,
        changes=len(repairs),
        detail={
            "violations": [
                {
                    "code": getattr(v, "code", None),
                    "severity": str(getattr(v, "severity", "")),
                    "phase": getattr(v, "phase", None),
                    "message": getattr(v, "message", ""),
                }
                for v in violations
            ],
            "repaired_surface": getattr(result, "repaired_surface", None),
        },
    )


def constrain(value: str, spec: Any) -> tuple[StageRecord, Any]:
    """Run mtg on ``value`` against ``spec`` and return (record, GuardResult).

    Lazily imports ``mtg``. Raises ImportError with guidance if absent.
    """
    try:
        import mtg  # type: ignore
    except Exception as e:  # noqa: BLE001
        raise ImportError(
            "mtg is required for constrain(); install it from "
            "https://github.com/Moshe-ship/mtg"
        ) from e
    result = mtg.run(value, spec)
    return record_from_mtg(result, getattr(mtg, "SEVERITY_TO_OUTCOME", None)), result


def record_from_toolproof(result: Any, detail: Optional[Mapping[str, Any]] = None) -> StageRecord:
    """Convert a toolproof ``VerificationResult`` (or ``Verdict``) into a
    VERIFY stage record. ``ok`` is True only for the VERIFIED verdict.
    """
    verdict = getattr(result, "verdict", result)
    name = getattr(verdict, "name", str(verdict)).upper()
    return StageRecord(
        stage=STAGE_VERIFY,
        tool="toolproof",
        ok=(name == "VERIFIED"),
        detail={"verdict": name, **(dict(detail) if detail else {})},
    )
