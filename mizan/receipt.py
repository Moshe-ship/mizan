"""The Mizan receipt — one audit format every stage of the scale shares.

Each reliability operation (restore, balance, classify, constrain, verify)
appends a `StageRecord` to a `Receipt`. Downstream tools (mtg, toolproof)
produce the same shape, so a single agent turn yields one weighable,
JSON-serialisable trail from input to execution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping


# Canonical stage names, in pipeline order. Tools attach to a stage.
STAGE_SCAN = "scan"              # mcpscan (tool-surface inspection, pre-pipeline)
STAGE_RESTORE = "restore"        # jabr
STAGE_BALANCE = "balance"        # muqabalah
STAGE_CLASSIFY = "classify"      # qadiya
STAGE_CONSTRAIN = "constrain"    # mtg
STAGE_VERIFY = "verify"          # toolproof


@dataclass(frozen=True)
class StageRecord:
    """One operation's contribution to the receipt.

    Attributes:
        stage: canonical pipeline stage (see STAGE_* constants).
        tool: the implementing tool, e.g. "jabr", "muqabalah".
        ok: False when the stage refused/blocked (contradiction, no case,
            violation, failed verification).
        changes: count of substantive changes the stage made.
        detail: tool-specific structured payload (must be JSON-serialisable).
    """

    stage: str
    tool: str
    ok: bool = True
    changes: int = 0
    detail: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "tool": self.tool,
            "ok": self.ok,
            "changes": self.changes,
            "detail": dict(self.detail),
        }


@dataclass(frozen=True)
class Receipt:
    """The weighable trail for one input as it crosses the scale.

    `ok` is the conjunction of every stage's `ok`: a receipt is clean only
    if no stage refused.
    """

    input: str
    output: str
    stages: tuple[StageRecord, ...] = ()

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.stages)

    @property
    def blocked_by(self) -> tuple[str, ...]:
        """Tools whose stage refused, in order."""
        return tuple(s.tool for s in self.stages if not s.ok)

    def with_stage(self, record: StageRecord, output: str | None = None) -> "Receipt":
        """Return a new receipt with `record` appended (immutable)."""
        return Receipt(
            input=self.input,
            output=self.output if output is None else output,
            stages=self.stages + (record,),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "output": self.output,
            "ok": self.ok,
            "blocked_by": list(self.blocked_by),
            "stages": [s.to_dict() for s in self.stages],
        }

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)
