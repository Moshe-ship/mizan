"""preflight — the input-integrity half of the scale, as one call.

Chains the two operations that gave algebra its name:

    restore (jabr)  ->  balance (muqabalah)

and emits a single :class:`~mizan.receipt.Receipt`. Contradictions are
fail-loud: ``preflight`` never silently resolves a conflict — it returns a
result with ``ok=False`` and the conflict surfaced, so the caller can ask a
clarifying question instead of letting the model guess.

The ``classify`` step (qadiya) is intentionally not part of free-text
preflight: qadiya operates on *structured* inputs (a proposed tool call and
its arguments), so it belongs to the dispatch/tool layer. The qadiya
primitives are re-exported from :mod:`mizan` for that purpose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

from mizan.receipt import (
    Receipt,
    StageRecord,
    STAGE_BALANCE,
    STAGE_RESTORE,
)

# jabr/muqabalah are installed from PyPI via `pip install mizan[preflight]`.
try:
    from jabr import restore, RestorationContext
    from muqabalah import (
        balance,
        CancellationContext,
        CancellationConflict,
    )
except ImportError as _exc:  # pragma: no cover - exercised only without primitives
    from mizan._primitives import missing_primitive

    raise missing_primitive(_exc.name or "jabr", "preflight") from _exc

# jabr annotates resolved spans with an inline tag: e.g. ``her[[jabr:1a2b]]``.
_JABR_TAG = re.compile(r"\[\[jabr:[0-9a-f]+\]\]")


def strip_tags(text: str) -> str:
    """Remove jabr's inline annotation tags, leaving human-readable text."""
    return _JABR_TAG.sub("", text)


@dataclass(frozen=True)
class PreflightContext:
    """Inputs to the preflight pass. All fields are optional.

    Args:
        now: reference time for date/relative-time resolution. Defaults to
            ``datetime.now()`` at call time when omitted.
        referents: pronoun -> name map for jabr (e.g. ``{"her": "Alice"}``).
        defaults: slot -> value map for jabr (e.g. ``{"channel": "#eng"}``).
        contradiction_predicates: conflicting term pairs for muqabalah
            (e.g. ``[("send", "cancel")]``).
    """

    now: datetime | None = None
    referents: Mapping[str, str] = field(default_factory=dict)
    defaults: Mapping[str, str] = field(default_factory=dict)
    contradiction_predicates: Sequence[tuple[str, str]] = ()


@dataclass(frozen=True)
class PreflightResult:
    """Outcome of :func:`preflight`.

    Attributes:
        ok: True when no contradiction was found.
        input: the original text.
        output: the annotated, balanced text (jabr tags preserved).
        clean_output: ``output`` with jabr tags stripped (readable).
        contradiction: human-readable conflict message, or ``None``.
        receipt: the weighable :class:`~mizan.receipt.Receipt`.
    """

    ok: bool
    input: str
    output: str
    clean_output: str
    contradiction: str | None
    receipt: Receipt

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "input": self.input,
            "output": self.output,
            "clean_output": self.clean_output,
            "contradiction": self.contradiction,
            "receipt": self.receipt.to_dict(),
        }


def preflight(text: str, ctx: PreflightContext | None = None) -> PreflightResult:
    """Run restore -> balance on ``text`` and return a single result.

    On contradiction, returns ``ok=False`` with the conflict surfaced; the
    receipt's balance stage is marked ``ok=False``. The original text is
    always recoverable from the receipt input.
    """
    ctx = ctx or PreflightContext()
    receipt = Receipt(input=text, output=text)

    # Step 1 — restore (jabr): make implicit terms explicit.
    rctx = RestorationContext(
        now=ctx.now or datetime.now(),
        referents=dict(ctx.referents),
        defaults=dict(ctx.defaults),
    )
    restored = restore(text, rctx)
    j_entries = list(getattr(restored.trace, "entries", ()) or ())
    receipt = receipt.with_stage(
        StageRecord(
            stage=STAGE_RESTORE,
            tool="jabr",
            ok=True,
            changes=len(j_entries),
            detail=_trace_detail(restored.trace),
        ),
        output=restored.output,
    )

    # Step 2 — balance (muqabalah): cancel duplicates, fail loud on conflict.
    cctx = CancellationContext(
        contradiction_predicates=list(ctx.contradiction_predicates)
    )
    try:
        balanced = balance(restored.output, cctx)
    except CancellationConflict as conflict:
        conflicts = [str(c) for c in (getattr(conflict, "conflicts", None) or [])]
        receipt = receipt.with_stage(
            StageRecord(
                stage=STAGE_BALANCE,
                tool="muqabalah",
                ok=False,
                changes=0,
                detail={"conflict": str(conflict), "conflicts": conflicts},
            )
        )
        return PreflightResult(
            ok=False,
            input=text,
            output=restored.output,
            clean_output=strip_tags(restored.output),
            contradiction=str(conflict),
            receipt=receipt,
        )

    m_entries = list(getattr(balanced.trace, "entries", ()) or ())
    receipt = receipt.with_stage(
        StageRecord(
            stage=STAGE_BALANCE,
            tool="muqabalah",
            ok=True,
            changes=len(m_entries),
            detail=_trace_detail(balanced.trace),
        ),
        output=balanced.output,
    )

    return PreflightResult(
        ok=True,
        input=text,
        output=balanced.output,
        clean_output=strip_tags(balanced.output),
        contradiction=None,
        receipt=receipt,
    )


def _trace_detail(trace: Any) -> dict[str, Any]:
    """Best-effort JSONable view of a jabr/muqabalah trace."""
    if trace is None:
        return {}
    if hasattr(trace, "to_dict"):
        try:
            return dict(trace.to_dict())
        except Exception:  # noqa: BLE001
            pass
    return {}
