"""Tests for the OpenAI Agents SDK adapter — no SDK required (plain callables)."""

from __future__ import annotations

import asyncio

import pytest

from mizan import receipt_v0
from mizan.adapters.openai import receipt_tool

SECRET = "adapter-secret"


def test_tool_call_emits_signed_verifiable_receipt():
    received = []

    @receipt_tool(secret=SECRET, key_id="local", sink=received.append, agent_id="a1", model="gpt-x", run_id="run-9")
    def get_weather(city: str) -> dict:
        return {"city": city, "temp": 72}

    assert get_weather("Riyadh") == {"city": "Riyadh", "temp": 72}

    assert len(received) == 1
    doc = received[0]
    assert doc == get_weather.last_receipt
    # structurally valid + signature verifies
    assert receipt_v0.structural_errors(doc) == []
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.OK
    # captured the right things
    assert doc["execution"]["tool"] == "get_weather"
    assert doc["execution"]["args_hash"].startswith("sha256:")
    assert doc["execution"]["result_hash"].startswith("sha256:")
    assert doc["execution"]["observed_status"] == "ok"
    assert doc["subject"] == {"agent_id": "a1", "model": "gpt-x", "run_id": "run-9", "tool": "get_weather"}
    assert doc["decision"]["action"] == "allowed"


def test_tampered_result_fails_verification():
    @receipt_tool(secret=SECRET)
    def add(a: int, b: int) -> int:
        return a + b

    add(2, 3)
    doc = add.last_receipt
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.OK
    doc["execution"]["result_hash"] = receipt_v0.hash_text("999")  # tamper after signing
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.TAMPERED


def test_error_is_recorded_and_reraised():
    @receipt_tool(secret=SECRET)
    def boom() -> None:
        raise ValueError("nope")

    with pytest.raises(ValueError):
        boom()
    doc = boom.last_receipt
    assert doc["execution"]["observed_status"] == "error"
    assert doc["execution"]["result_hash"] is None
    assert doc["decision"]["action"] == "blocked"  # failing stage → blocked
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.OK  # the receipt itself is signed/valid


def test_unsigned_when_no_secret():
    @receipt_tool()
    def noop() -> int:
        return 1

    noop()
    assert noop.last_receipt["signature"]["value"] is None
    assert receipt_v0.verify(noop.last_receipt, SECRET) == receipt_v0.UNSIGNED


def test_async_tool_supported():
    @receipt_tool(secret=SECRET)
    async def fetch(x: int) -> int:
        return x * 2

    assert asyncio.run(fetch(21)) == 42
    assert receipt_v0.verify(fetch.last_receipt, SECRET) == receipt_v0.OK
    assert fetch.last_receipt["execution"]["tool"] == "fetch"


def test_leading_context_excluded_from_args_hash():
    class RunContextWrapper:  # duck-types the SDK's context object
        def __init__(self):
            self.context = {}

    @receipt_tool(secret=SECRET)
    def read_file(ctx, path: str) -> str:
        return "data"

    read_file(RunContextWrapper(), "/etc/hosts")
    h_with_ctx = read_file.last_receipt["execution"]["args_hash"]

    @receipt_tool(secret=SECRET, tool_name="read_file")
    def read_file_noctx(path: str) -> str:
        return "data"

    read_file_noctx("/etc/hosts")
    h_noctx = read_file_noctx.last_receipt["execution"]["args_hash"]
    # context object must not change the args hash
    assert h_with_ctx == h_noctx


def test_signature_preserved_for_sdk_introspection():
    import inspect

    @receipt_tool(secret=SECRET)
    def typed(city: str, days: int = 1) -> dict:
        return {}

    sig = inspect.signature(typed)  # SDK derives schema from this
    assert list(sig.parameters) == ["city", "days"]
    assert typed.__name__ == "typed"
