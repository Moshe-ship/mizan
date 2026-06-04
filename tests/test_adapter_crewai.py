"""Real CrewAI adapter smoke test.

Skipped unless `crewai` is installed (`pip install "mizan[crewai]"`). Nothing is
mocked: it builds real CrewAI `@tool` tools and invokes them via `.run()` — the
same path an Agent/Crew uses — asserting a signed, verifiable Receipt v0 for the
compose, wrap, and error paths.

Verified against crewai 1.14.x on Python 3.11 (CrewAI's native deps — e.g.
tiktoken — currently build on 3.11/3.12, so CI runs this in a dedicated 3.11
job rather than across the whole matrix).
"""

from __future__ import annotations

import pytest

pytest.importorskip("crewai")

from crewai.tools import tool  # noqa: E402

from mizan import receipt_v0  # noqa: E402
from mizan.adapters.crewai import receipt_tool, wrap_tool, wrap_tools  # noqa: E402

SECRET = "crewai-test-secret"


def test_compose_under_tool_emits_receipt():
    sink = []

    @tool("get_weather")
    @receipt_tool(secret=SECRET, sink=sink.append, agent_id="a1", run_id="run-1")
    def get_weather(city: str) -> dict:
        """Get the weather for a city."""
        return {"city": city, "temp": 72}

    assert get_weather.run(city="Riyadh") == {"city": "Riyadh", "temp": 72}
    assert len(sink) == 1
    doc = sink[0]
    assert receipt_v0.structural_errors(doc) == []
    assert receipt_v0.verify(doc, SECRET) == receipt_v0.OK
    assert doc["execution"]["tool"] == "get_weather"
    assert doc["execution"]["observed_status"] == "ok"
    assert doc["subject"]["run_id"] == "run-1"


def test_wrap_existing_tool_emits_receipt():
    @tool("add")
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    sink = []
    guarded = wrap_tool(add, secret=SECRET, sink=sink.append)
    assert guarded.run(a=2, b=3) == 5
    assert len(sink) == 1
    assert receipt_v0.verify(sink[0], SECRET) == receipt_v0.OK
    assert sink[0]["execution"]["tool"] == "add"


def test_wrap_tools_list_and_error_path():
    @tool("boom")
    def boom() -> int:
        """Always fails."""
        raise ValueError("kaboom")

    sink = []
    guarded = wrap_tools([boom], secret=SECRET, sink=sink.append)
    assert len(guarded) == 1
    try:
        guarded[0].run()
    except Exception:
        pass
    assert len(sink) == 1, "no receipt on the error path"
    assert sink[0]["execution"]["observed_status"] == "error"
    assert receipt_v0.verify(sink[0], SECRET) == receipt_v0.OK


if __name__ == "__main__":
    test_compose_under_tool_emits_receipt()
    test_wrap_existing_tool_emits_receipt()
    test_wrap_tools_list_and_error_path()
    print("PASS (CrewAI present)")
