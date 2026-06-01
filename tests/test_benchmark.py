"""Regression guard for the MCP-poisoning benchmark.

Fails if the consistency set ever misses a known pattern or a clean tool gets a
hard (high-severity) false positive. The full per-category report lives in
docs/MCP_POISONING_BENCHMARK.md (regenerate with `python benchmark/run.py`).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "benchmark"))

import run  # noqa: E402  (benchmark/run.py)


def test_consistency_set_fully_caught_and_no_hard_false_positives():
    _, regression_ok = run.build_report()
    assert regression_ok, "consistency-set miss or a hard false positive — see `python benchmark/run.py`"


def test_corpus_splits_are_nonempty_and_labeled():
    consistency = run._load("consistency")
    heldout = run._load("heldout")
    clean = run._load("clean")
    assert len(consistency) >= 20 and all(i["label"] == "poison" for i in consistency)
    assert len(heldout) >= 10 and all(i["label"] == "poison" for i in heldout)
    assert len(clean) >= 30 and all(i["label"] == "clean" for i in clean)
