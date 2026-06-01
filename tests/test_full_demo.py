"""Smoke test for the end-to-end killer demo (needs the full pipeline)."""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

pytest.importorskip("mtg")
pytest.importorskip("toolproof")

from mizan import receipt_v0  # noqa: E402

DEMO = pathlib.Path(__file__).resolve().parent.parent / "examples" / "full_pipeline_demo.py"
RECEIPT = pathlib.Path("/tmp/mizan-demo-receipt.json")


def test_demo_runs_and_emits_a_verifiable_receipt(tmp_path):
    repo = pathlib.Path(__file__).resolve().parent.parent
    env = {**os.environ, "PYTHONPATH": f"{repo}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
    proc = subprocess.run([sys.executable, str(DEMO)], capture_output=True, text=True, env=env)
    assert proc.returncode == 0, proc.stderr
    # all eight steps printed
    for marker in ["[1/8]", "[5/8]", "[8/8]", "tampered"]:
        assert marker in proc.stdout, proc.stdout

    doc = json.loads(RECEIPT.read_text())
    # the written receipt is the untampered one → verifies
    assert receipt_v0.verify(doc, "demo-secret") == receipt_v0.OK
    # and it captured the pipeline catching things
    assert doc["decision"]["action"] == "blocked"
    assert receipt_v0.structural_errors(doc) == []

    # tampering it must fail
    doc["stages"][0]["ok"] = True
    assert receipt_v0.verify(doc, "demo-secret") == receipt_v0.TAMPERED
