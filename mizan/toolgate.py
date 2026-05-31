"""toolgate — constraint-driven tool-call gating, built on qadiya.

This is the ``classify`` step of the scale applied to a *proposed tool call*.
Instead of an ad-hoc allow/block list, a :class:`ToolGate` enumerates the
complete case space from a constraint set, marks the allowed cases, and
escalates everything else. The architectural guarantee is qadiya's:

    an input that matches no allowed case is escalated, never silently run.

A gate decision carries a :class:`~mizan.receipt.StageRecord` so it appends
to the same receipt as preflight, mtg, and toolproof.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from mizan.receipt import StageRecord, STAGE_CLASSIFY

try:
    from qadiya import (
        CaseRegistry,
        Constraint,
        Dispatch,
        DispatchOutcome,
        NoMatchingCase,
    )
except ImportError as _exc:  # pragma: no cover - exercised only without primitives
    from mizan._primitives import missing_primitive

    raise missing_primitive("qadiya", "toolgate") from _exc

# Sentinel value any membership constraint folds unlisted values into, so the
# constraint stays total (every input maps to a declared value).
OTHER = "__other__"


def equals_constraint(
    name: str, key: str, allowed: Sequence[str]
) -> Constraint:
    """A membership constraint over ``input[key]``.

    Evaluates to the value when it is one of ``allowed``, otherwise to
    :data:`OTHER`. Totality is guaranteed, so classification never raises on
    an unexpected value — it routes to the ``OTHER`` case (which is escalated
    unless explicitly allowed).
    """
    values = tuple(allowed) + (OTHER,)

    def _eval(inp: Mapping[str, Any]) -> str:
        v = inp.get(key)
        return v if v in values else OTHER

    return Constraint(name=name, values=values, evaluate=_eval)


def predicate_constraint(
    name: str, predicate: Callable[[Mapping[str, Any]], bool]
) -> Constraint:
    """A binary constraint: ``True``/``False`` from ``predicate(input)``."""
    return Constraint(
        name=name,
        values=(True, False),
        evaluate=lambda inp: bool(predicate(inp)),
    )


@dataclass(frozen=True)
class GateDecision:
    """Outcome of :meth:`ToolGate.check`."""

    allowed: bool
    case_id: str
    evaluated: dict[str, Any]
    reason: str
    record: StageRecord


def _allow(_inp: Any) -> bool:  # registered procedure for allowed cases
    return True


class ToolGate:
    """Allowlist a set of cases over a constraint set; escalate the rest.

    Args:
        constraints: ordered qadiya constraints evaluated against a tool-call
            dict (typically ``{"tool_name": ..., "args": {...}, ...}``).
        allowed_case_ids: case_ids permitted to run. Every other enumerated
            case is escalated (blocked).
        feasible: optional predicate to prune impossible constraint combos.

    Raises:
        ValueError: if an ``allowed_case_ids`` entry is not an enumerated
            case (catches typos and stale policy at construction time).
    """

    def __init__(
        self,
        constraints: list[Constraint],
        allowed_case_ids: Sequence[str],
        *,
        feasible: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        self.registry: CaseRegistry = CaseRegistry(
            constraints=constraints, feasible=feasible
        )
        valid = {c.case_id for c in self.registry.cases}
        allowed = set(allowed_case_ids)
        unknown = allowed - valid
        if unknown:
            raise ValueError(
                f"allowed_case_ids not in enumerated cases: {sorted(unknown)}. "
                f"Valid: {sorted(valid)}"
            )
        for case in self.registry.cases:
            if case.case_id in allowed:
                self.registry.register(case.case_id, _allow, name="allow")
            else:
                self.registry.escalate(case.case_id)
        self.registry.verify_complete()
        self._dispatch: Dispatch = Dispatch(registry=self.registry)

    @property
    def cases(self) -> list[str]:
        return [c.case_id for c in self.registry.cases]

    def check(self, tool_call: Mapping[str, Any]) -> GateDecision:
        """Classify a proposed tool call and decide allow vs escalate."""
        try:
            result = self._dispatch(dict(tool_call))
        except NoMatchingCase as e:  # defensive — should not occur (total)
            rec = StageRecord(
                stage=STAGE_CLASSIFY,
                tool="qadiya",
                ok=False,
                detail={"reason": "no_matching_case", "evaluated": e.evaluated_constraints},
            )
            return GateDecision(
                allowed=False,
                case_id="",
                evaluated=e.evaluated_constraints,
                reason="no matching case — escalated",
                record=rec,
            )

        allowed = result.outcome == DispatchOutcome.DISPATCHED
        reason = (
            f"case {result.case_id} allowed"
            if allowed
            else f"case {result.case_id} not in allowlist — escalated"
        )
        rec = StageRecord(
            stage=STAGE_CLASSIFY,
            tool="qadiya",
            ok=allowed,
            detail={"case_id": result.case_id, "evaluated": result.evaluated_constraints},
        )
        return GateDecision(
            allowed=allowed,
            case_id=result.case_id,
            evaluated=result.evaluated_constraints,
            reason=reason,
            record=rec,
        )
