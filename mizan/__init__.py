"""Mizan ميزان — the reliability scale for AI agents.

One front door for the input-integrity half of the stack:

    >>> from mizan import preflight, PreflightContext
    >>> r = preflight("send it. cancel it.",
    ...               PreflightContext(contradiction_predicates=[("send", "cancel")]))
    >>> r.ok
    False
    >>> r.contradiction is not None
    True

The qadiya case primitives are re-exported for the dispatch/tool layer, and
the shared :class:`Receipt` is the one audit format every stage appends to.
"""

from __future__ import annotations

from mizan.preflight import (
    PreflightContext,
    PreflightResult,
    preflight,
    strip_tags,
)
from mizan.receipt import (
    Receipt,
    StageRecord,
    STAGE_BALANCE,
    STAGE_CLASSIFY,
    STAGE_CONSTRAIN,
    STAGE_RESTORE,
    STAGE_SCAN,
    STAGE_VERIFY,
)
from mizan.integrations import (
    record_from_mtg,
    record_from_toolproof,
    constrain,
)

# Re-export the qadiya case layer (classify + dispatch) for tool gating.
# Imported defensively so `import mizan` still works if qadiya is absent.
try:
    from qadiya import (  # noqa: F401
        Case,
        Constraint,
        CaseRegistry,
        Classifier,
        Dispatch,
        DispatchResult,
        DispatchOutcome,
        NoMatchingCase,
        AmbiguousCases,
        enumerate_cases,
    )
    from mizan.toolgate import (  # noqa: F401
        ToolGate,
        GateDecision,
        equals_constraint,
        predicate_constraint,
        OTHER,
    )

    _HAS_QADIYA = True
except Exception:  # noqa: BLE001
    _HAS_QADIYA = False

# mcpscan needs mtg; import defensively so `import mizan` works without it.
try:
    from mizan.mcpscan import (  # noqa: F401
        scan_tool,
        scan_tools,
        ScanResult,
        Finding,
        ScanConfig,
        Decision,
        decide,
        report,
    )

    _HAS_MCPSCAN = True
except Exception:  # noqa: BLE001
    _HAS_MCPSCAN = False

__version__ = "0.1.0"

__all__ = [
    "preflight",
    "PreflightContext",
    "PreflightResult",
    "strip_tags",
    "Receipt",
    "StageRecord",
    "STAGE_RESTORE",
    "STAGE_BALANCE",
    "STAGE_CLASSIFY",
    "STAGE_CONSTRAIN",
    "STAGE_SCAN",
    "STAGE_VERIFY",
    "record_from_mtg",
    "record_from_toolproof",
    "constrain",
    "__version__",
]

if _HAS_QADIYA:
    __all__ += [
        "Case",
        "Constraint",
        "CaseRegistry",
        "Classifier",
        "Dispatch",
        "DispatchResult",
        "DispatchOutcome",
        "NoMatchingCase",
        "AmbiguousCases",
        "enumerate_cases",
        "ToolGate",
        "GateDecision",
        "equals_constraint",
        "predicate_constraint",
        "OTHER",
    ]

if _HAS_MCPSCAN:
    __all__ += [
        "scan_tool", "scan_tools", "ScanResult", "Finding",
        "ScanConfig", "Decision", "decide", "report",
    ]
