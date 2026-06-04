"""Signed Receipts for LangGraph / LangChain tool calls.

Runs the real LangChain tool runtime when `langchain-core` is installed (no LLM
needed — it invokes the tool the way a LangGraph ToolNode does), else a plain
callable on a bare `pip install mizan`.

    pip install "mizan[langgraph]"
    python examples/langgraph_receipt.py
    MIZAN_RECEIPT_SECRET=demo-secret mizan verify-log /tmp/lg-receipts.jsonl --secret-env MIZAN_RECEIPT_SECRET
    MIZAN_RECEIPT_SECRET=demo-secret mizan report  /tmp/lg-receipts.jsonl --secret-env MIZAN_RECEIPT_SECRET --open

In an app you hand the wrapped tools to your graph:

    from mizan.adapters.langgraph import wrap_tools, chain_sink
    from langgraph.prebuilt import create_react_agent
    guarded = wrap_tools(my_tools, secret=SECRET, sink=chain_sink("receipts.jsonl"))
    agent = create_react_agent(model, guarded)           # every tool call leaves a receipt
"""

from __future__ import annotations

import json

from mizan import receipt_v0
from mizan.adapters.langgraph import chain_sink, receipt_tool

SECRET = "demo-secret"
LOG = "/tmp/lg-receipts.jsonl"


def main() -> None:
    open(LOG, "w").close()
    sink = chain_sink(LOG)

    try:
        from langchain_core.tools import tool

        @tool
        @receipt_tool(secret=SECRET, key_id="local", agent_id="concierge", sink=sink)
        def get_weather(city: str) -> dict:
            """Get the weather for a city."""
            return {"city": city, "temp": 72}

        result = get_weather.invoke({"city": "Riyadh"})   # the LangGraph ToolNode path
        mode = "real LangChain tool (.invoke)"
    except Exception:
        @receipt_tool(secret=SECRET, key_id="local", agent_id="concierge", sink=sink)
        def get_weather(city: str) -> dict:
            return {"city": city, "temp": 72}

        result = get_weather("Riyadh")
        mode = "plain callable (install mizan[langgraph] for the real path)"

    print(f"mode: {mode}")
    print(f"tool returned: {result}")
    last = [json.loads(l)["receipt"] for l in open(LOG)][-1]
    print(f"signed receipt: tool={last['execution']['tool']} "
          f"status={last['execution']['observed_status']} "
          f"valid={receipt_v0.verify(last, SECRET) == receipt_v0.OK}")
    print(f"\n  verify: MIZAN_RECEIPT_SECRET={SECRET} mizan verify-log {LOG} --secret-env MIZAN_RECEIPT_SECRET")


if __name__ == "__main__":
    main()
