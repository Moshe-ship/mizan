"""Real LangGraph / LangChain adapter smoke test.

Skipped unless `langchain-core` is installed (`pip install "mizan[langgraph]"`).
Drives the actual LangChain tool runtime: builds a tool, invokes it via
`.invoke()` exactly as a LangGraph ToolNode does, and asserts a signed,
verifiable Receipt v0 — for both the compose-under-`@tool` and `wrap_tool`
paths, and on the error path.
"""

from __future__ import annotations

import pytest

pytest.importorskip("langchain_core")

from langchain_core.tools import tool  # noqa: E402

from mizan import receipt_v0  # noqa: E402
from mizan.adapters.langgraph import receipt_tool, wrap_tool, wrap_tools  # noqa: E402

SECRET = "lg-test-secret"


def test_compose_under_tool_emits_receipt():
    sink = []

    @tool
    @receipt_tool(secret=SECRET, sink=sink.append, agent_id="a1", run_id="run-1")
    def get_weather(city: str) -> dict:
        """Get the weather for a city."""
        return {"city": city, "temp": 72}

    assert "city" in get_weather.args_schema.model_json_schema().get("properties", {})
    assert get_weather.invoke({"city": "Riyadh"}) == {"city": "Riyadh", "temp": 72}

    assert len(sink) == 1
    doc = sink[0]
    assert receipt_v0.structural_errors(doc) == []
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.OK
    assert doc["execution"]["tool"] == "get_weather"
    assert doc["execution"]["observed_status"] == "ok"
    assert doc["subject"]["run_id"] == "run-1"


def test_wrap_existing_tool_emits_receipt():
    @tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    sink = []
    guarded = wrap_tool(add, secret=SECRET, sink=sink.append)
    assert guarded.name == "add"
    assert guarded.invoke({"a": 2, "b": 3}) == 5
    assert len(sink) == 1
    assert receipt_v0.verify(sink[0], SECRET) == receipt_v0.OK
    assert sink[0]["execution"]["tool"] == "add"


def test_wrap_tools_list_and_error_path():
    @tool
    def boom() -> int:
        """Always fails."""
        raise ValueError("kaboom")

    sink = []
    guarded = wrap_tools([boom], secret=SECRET, sink=sink.append)
    assert len(guarded) == 1
    try:
        guarded[0].invoke({})
    except Exception:
        pass
    assert len(sink) == 1, "no receipt on the error path"
    assert sink[0]["execution"]["observed_status"] == "error"
    assert receipt_v0.verify(sink[0], SECRET) == receipt_v0.OK


if __name__ == "__main__":
    test_compose_under_tool_emits_receipt()
    test_wrap_existing_tool_emits_receipt()
    test_wrap_tools_list_and_error_path()
    print("PASS (LangChain present)")
