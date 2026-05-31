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
from mizan.otel import receipt_to_spans, emit as emit_otel

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

# Version comes from installed package metadata so it never drifts from
# pyproject.toml. Falls back when running from an uninstalled source tree.
try:
    from importlib.metadata import version as _pkg_version, PackageNotFoundError

    __version__ = _pkg_version("mizan")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    __version__ = "0.0.0+source"

# The preflight (jabr/muqabalah) layer is imported lazily so that `import
# mizan` and the standalone mizan.mcpscan scanner work WITHOUT the
# not-yet-published primitive packages. Accessing a preflight symbol triggers
# the import and, if a primitive is missing, raises a friendly
# MissingPrimitiveError (see mizan._primitives) instead of a bare ImportError.
_LAZY_PREFLIGHT = {"preflight", "PreflightContext", "PreflightResult", "strip_tags"}


def __getattr__(name: str):
    if name in _LAZY_PREFLIGHT:
        import importlib

        module = importlib.import_module("mizan.preflight")
        # Bind ALL preflight symbols at once. Importing the submodule makes the
        # import system bind `mizan.preflight` to the *module*; we must rebind
        # `preflight` to the *function* regardless of which name triggered this,
        # or a later `from mizan import preflight` would get a non-callable module.
        for _sym in _LAZY_PREFLIGHT:
            globals()[_sym] = getattr(module, _sym)
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | _LAZY_PREFLIGHT)


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
    "receipt_to_spans",
    "emit_otel",
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
