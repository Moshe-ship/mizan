"""Real OpenAI Agents SDK integration smoke test.

Skipped unless `openai-agents` is installed (`pip install "mizan[openai]"`).
Unlike test_adapter_openai.py (plain callables), this drives the *actual* SDK:
it builds a `FunctionTool` via `@function_tool` composed over `receipt_tool`,
then invokes it exactly as the SDK runtime does (`tool.on_invoke_tool(ctx,
json_args)`) and asserts a signed, verifiable Receipt v0 was emitted — on both
the success and error paths.
"""

from __future__ import annotations

import asyncio
import json

import pytest

agents = pytest.importorskip("agents")  # skip cleanly when the SDK isn't installed

from agents import function_tool  # noqa: E402

from mizan import receipt_v0  # noqa: E402
from mizan.adapters.openai import receipt_tool  # noqa: E402

SECRET = "sdk-test-secret"


def _ctx(tool_name: str, args_json: str):
    """A ToolContext like the SDK passes to on_invoke_tool (version-tolerant)."""
    from agents.tool_context import ToolContext
    try:
        return ToolContext(context=None, tool_name=tool_name,
                           tool_call_id="call_1", tool_arguments=args_json)
    except TypeError:
        from agents.run_context import RunContextWrapper
        return RunContextWrapper(context=None)


def _invoke(tool, args_json: str):
    return asyncio.run(tool.on_invoke_tool(_ctx(tool.name, args_json), args_json))


def test_sdk_function_tool_emits_signed_receipt():
    sink = []

    @function_tool
    @receipt_tool(secret=SECRET, key_id="local", sink=sink.append,
                  agent_id="a1", model="gpt-x", run_id="run-1")
    def get_weather(city: str) -> dict:
        """Get the weather for a city."""
        return {"city": city, "temp": 72}

    # the SDK derived the schema from the wrapped signature
    assert get_weather.name == "get_weather"
    assert "city" in get_weather.params_json_schema.get("properties", {})

    # invoke the way the SDK runtime does
    result = _invoke(get_weather, '{"city": "Riyadh"}')
    assert result == {"city": "Riyadh", "temp": 72}

    assert len(sink) == 1
    doc = sink[0]
    assert receipt_v0.structural_errors(doc) == []
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.OK
    assert doc["execution"]["tool"] == "get_weather"
    assert doc["execution"]["observed_status"] == "ok"
    assert doc["subject"]["run_id"] == "run-1"


def test_sdk_tool_error_path_still_receipts():
    sink = []

    @function_tool
    @receipt_tool(secret=SECRET, sink=sink.append)
    def boom(x: int) -> int:
        """Always fails."""
        raise ValueError("kaboom")

    # The SDK captures tool errors; whether it raises or returns an error string,
    # a receipt recording the failed execution must still be emitted.
    try:
        _invoke(boom, '{"x": 1}')
    except Exception:
        pass

    assert len(sink) == 1, "no receipt emitted on the error path"
    doc = sink[0]
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.OK
    assert doc["execution"]["observed_status"] == "error"


if __name__ == "__main__":
    test_sdk_function_tool_emits_signed_receipt()
    test_sdk_tool_error_path_still_receipts()
    print("PASS (SDK present)")
