"""Signed Receipts for OpenAI Agents SDK tool calls.

Run your agent normally; Mizan gives every tool action a signed receipt you can
verify later. This file runs on a bare `pip install mizan` (no SDK needed) to
demonstrate the receipt; the commented block shows the real SDK composition.

    python examples/openai_agents_receipt.py
    mizan verify /tmp/weather-receipt.json --secret-env MIZAN_RECEIPT_SECRET
"""

from __future__ import annotations

import json

from mizan import receipt_v0
from mizan.adapters.openai import receipt_tool

SECRET = "demo-secret"  # in production: load from env / a secret manager

# --- Real OpenAI Agents SDK usage (needs: pip install "mizan[openai]") --------
#
#     from agents import Agent, Runner, function_tool
#     from mizan.adapters.openai import receipt_tool, jsonl_sink
#
#     @function_tool                                   # SDK derives the schema
#     @receipt_tool(secret=SECRET, key_id="local",     # Mizan signs each call
#                   sink=jsonl_sink("receipts.jsonl"))
#     def get_weather(city: str) -> dict:
#         return {"city": city, "temp": 72}
#
#     agent = Agent(name="concierge", tools=[get_weather])
#     Runner.run_sync(agent, "What's the weather in Riyadh?")
#     # every get_weather call appended a signed receipt to receipts.jsonl
# ------------------------------------------------------------------------------


@receipt_tool(secret=SECRET, key_id="local", agent_id="concierge", model="gpt-x")
def get_weather(city: str) -> dict:
    return {"city": city, "temp": 72}


def main() -> None:
    result = get_weather("Riyadh")
    receipt = get_weather.last_receipt

    path = "/tmp/weather-receipt.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2)

    print(f"tool returned: {result}")
    print(f"receipt: {path}")
    print(f"  tool={receipt['execution']['tool']}  status={receipt['execution']['observed_status']}")
    print(f"  args_hash={receipt['execution']['args_hash'][:23]}…")
    print(f"  signature valid: {receipt_v0.verify(receipt, SECRET) == receipt_v0.OK}")
    print(f"\n  verify it: MIZAN_RECEIPT_SECRET={SECRET} mizan verify {path}")


if __name__ == "__main__":
    main()
