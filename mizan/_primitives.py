"""Friendly errors for mizan's optional primitive packages.

The reliability pipeline (``preflight``, ``toolgate``, ``verify``) builds on
five primitives — jabr, muqabalah, qadiya, mtg, toolproof — that are not yet
on PyPI. The ``mizan.mcpscan`` scanner needs none of them.

When a primitive is imported but missing, raise a clear, actionable error
instead of a bare ``ModuleNotFoundError: No module named 'jabr'``.
"""

from __future__ import annotations

#: The optional primitive packages, in pipeline order.
PRIMITIVES = ("jabr", "muqabalah", "qadiya", "mtg", "toolproof")


class MissingPrimitiveError(ImportError):
    """An optional mizan primitive was imported but is not installed."""


def missing_primitive(name: str, feature: str) -> "MissingPrimitiveError":
    """Build a :class:`MissingPrimitiveError` naming *name* and how to install it."""
    extra = "verify" if feature == "verify" else "preflight"
    return MissingPrimitiveError(
        f"mizan.{feature} requires the '{name}' package, which isn't installed. "
        f"Install the reliability pipeline from PyPI:\n"
        f"    pip install 'mizan[{extra}]'   # or: pip install 'mizan[all]'\n"
        f"(The mizan.mcpscan scanner works without any primitives.)"
    )
