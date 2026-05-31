"""Friendly errors for mizan's optional primitive packages.

The reliability pipeline (``preflight``, ``toolgate``, ``verify``) builds on
five primitives — jabr, muqabalah, qadiya, mtg, toolproof — that are not yet
on PyPI. The ``mizan.mcpscan`` scanner needs none of them.

When a primitive is imported but missing, raise a clear, actionable error
instead of a bare ``ModuleNotFoundError: No module named 'jabr'``.
"""

from __future__ import annotations

_GIT_OWNER = "https://github.com/Moshe-ship"

#: The optional primitive packages, in pipeline order.
PRIMITIVES = ("jabr", "muqabalah", "qadiya", "mtg", "toolproof")


class MissingPrimitiveError(ImportError):
    """An optional mizan primitive was imported but is not installed."""


def missing_primitive(name: str, feature: str) -> "MissingPrimitiveError":
    """Build a :class:`MissingPrimitiveError` naming *name* and how to install it."""
    return MissingPrimitiveError(
        f"mizan.{feature} requires '{name}', which is not yet on PyPI. "
        f"Install it from git:\n"
        f"    pip install git+{_GIT_OWNER}/{name}.git\n"
        f"(The mizan.mcpscan scanner works without any primitives.)"
    )
