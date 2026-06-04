"""Signed Receipts for CrewAI tool calls.

Runs the real CrewAI tool runtime when `crewai` is installed (no LLM needed — it
invokes the tool via `.run()` the way an Agent does), else a plain callable on a
bare `pip install mizan`.

    pip install "mizan[crewai]"          # needs Python 3.11/3.12 (heavy native deps)
    python examples/crewai_receipt.py
    MIZAN_RECEIPT_SECRET=demo-secret mizan verify-log /tmp/crewai-receipts.jsonl --secret-env MIZAN_RECEIPT_SECRET
    MIZAN_RECEIPT_SECRET=demo-secret mizan report  /tmp/crewai-receipts.jsonl --secret-env MIZAN_RECEIPT_SECRET --open

In an app you hand the wrapped tools to your Agent/Crew:

    from mizan.adapters.crewai import wrap_tools, chain_sink
    guarded = wrap_tools(my_tools, secret=SECRET, sink=chain_sink("receipts.jsonl"))
    agent = Agent(role="concierge", tools=guarded, ...)   # every tool call leaves a receipt
"""

from __future__ import annotations

import json

from mizan import receipt_v0
from mizan.adapters.crewai import chain_sink, receipt_tool

SECRET = "demo-secret"
LOG = "/tmp/crewai-receipts.jsonl"


def main() -> None:
    open(LOG, "w").close()
    sink = chain_sink(LOG)

    try:
        from crewai.tools import tool

        @tool("get_weather")
        @receipt_tool(secret=SECRET, key_id="local", agent_id="concierge", sink=sink)
        def get_weather(city: str) -> dict:
            """Get the weather for a city."""
            return {"city": city, "temp": 72}

        result = get_weather.run(city="Riyadh")          # the CrewAI Agent path
        mode = "real CrewAI tool (.run)"
    except Exception:
        @receipt_tool(secret=SECRET, key_id="local", agent_id="concierge", sink=sink)
        def get_weather(city: str) -> dict:
            return {"city": city, "temp": 72}

        result = get_weather("Riyadh")
        mode = "plain callable (install mizan[crewai] on py3.11/3.12 for the real path)"

    print(f"mode: {mode}")
    print(f"tool returned: {result}")
    last = [json.loads(l)["receipt"] for l in open(LOG)][-1]
    print(f"signed receipt: tool={last['execution']['tool']} "
          f"status={last['execution']['observed_status']} "
          f"valid={receipt_v0.verify(last, SECRET) == receipt_v0.OK}")
    print(f"\n  verify: MIZAN_RECEIPT_SECRET={SECRET} mizan verify-log {LOG} --secret-env MIZAN_RECEIPT_SECRET")


if __name__ == "__main__":
    main()
