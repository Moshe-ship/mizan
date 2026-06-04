"""Signed Receipts for OpenAI Agents SDK tool calls.

Give every agent tool action a signed receipt you can verify later. This example
runs the **real SDK path** when `openai-agents` is installed (no API key needed —
it invokes the tool the way the SDK runtime does), and falls back to a plain
callable on a bare `pip install mizan`.

    pip install "mizan[openai]"
    python examples/openai_agents_receipt.py
    MIZAN_RECEIPT_SECRET=demo-secret mizan verify-log /tmp/agent-receipts.jsonl --secret-env MIZAN_RECEIPT_SECRET
    MIZAN_RECEIPT_SECRET=demo-secret mizan report  /tmp/agent-receipts.jsonl --secret-env MIZAN_RECEIPT_SECRET --open

In a real app you just run your agent normally — every tool call appends a
signed receipt to the chain:

    from agents import Agent, Runner, function_tool
    from mizan.adapters.openai import receipt_tool, chain_sink

    @function_tool                                       # SDK derives the schema
    @receipt_tool(secret=SECRET, sink=chain_sink("receipts.jsonl"))
    def get_weather(city: str) -> dict:
        return {"city": city, "temp": 72}

    agent = Agent(name="concierge", tools=[get_weather])
    Runner.run_sync(agent, "Weather in Riyadh?")         # needs OPENAI_API_KEY
"""

from __future__ import annotations

import asyncio
import json

from mizan import receipt_v0
from mizan.adapters.openai import chain_sink, receipt_tool

SECRET = "demo-secret"  # in production: load from env / a secret manager
LOG = "/tmp/agent-receipts.jsonl"


def _build_tool(sink):
    @receipt_tool(secret=SECRET, key_id="local", agent_id="concierge",
                  model="gpt-x", sink=sink)
    def get_weather(city: str) -> dict:
        """Get the weather for a city."""
        return {"city": city, "temp": 72}
    return get_weather


def main() -> None:
    open(LOG, "w").close()  # fresh log
    sink = chain_sink(LOG)

    try:
        from agents import function_tool  # the real SDK
        tool = function_tool(_build_tool(sink))
        from agents.tool_context import ToolContext
        ctx = ToolContext(context=None, tool_name=tool.name,
                          tool_call_id="call_1", tool_arguments='{"city": "Riyadh"}')
        result = asyncio.run(tool.on_invoke_tool(ctx, '{"city": "Riyadh"}'))
        mode = "real OpenAI Agents SDK (FunctionTool.on_invoke_tool)"
    except Exception:
        tool = _build_tool(sink)
        result = tool("Riyadh")
        mode = "plain callable (install mizan[openai] for the real SDK path)"

    print(f"mode: {mode}")
    print(f"tool returned: {result}")
    print(f"signed receipt appended to: {LOG}")
    last = [json.loads(l)["receipt"] for l in open(LOG)][-1]
    print(f"  tool={last['execution']['tool']}  status={last['execution']['observed_status']}")
    print(f"  signature valid: {receipt_v0.verify(last, SECRET) == receipt_v0.OK}")
    print(f"\n  verify: MIZAN_RECEIPT_SECRET={SECRET} mizan verify-log {LOG} --secret-env MIZAN_RECEIPT_SECRET")


if __name__ == "__main__":
    main()
