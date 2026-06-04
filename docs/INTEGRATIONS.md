# Integrations

Mizan emits a **signed Receipt v0** for every guarded tool action, whatever
framework runs your agent. Adapters are import-safe: the core never imports a
framework SDK; you opt in via an extra.

## OpenAI Agents SDK

```bash
pip install "mizan[openai]"     # adds openai-agents; core needs none
```

Compose `receipt_tool` **under** the SDK's `@function_tool` so the SDK still
derives the schema from the original signature. Each call appends a signed
receipt to a hash-chained log:

```python
from agents import Agent, Runner, function_tool
from mizan.adapters.openai import receipt_tool, chain_sink

@function_tool                                          # SDK derives the schema
@receipt_tool(secret="…", sink=chain_sink("receipts.jsonl"))
def get_weather(city: str) -> dict:
    return {"city": city, "temp": 72}

agent = Agent(name="concierge", tools=[get_weather])
Runner.run_sync(agent, "Weather in Riyadh?")            # needs OPENAI_API_KEY
```

Every `get_weather` call appends a signed Receipt v0 recording the hashed args,
hashed result, and observed status. Verify and view:

```bash
MIZAN_RECEIPT_SECRET=… mizan verify-log receipts.jsonl --secret-env MIZAN_RECEIPT_SECRET
MIZAN_RECEIPT_SECRET=… mizan report     receipts.jsonl --secret-env MIZAN_RECEIPT_SECRET --open
```

**Sinks:** `chain_sink(path)` → tamper-evident, `mizan verify-log`-able chain;
`jsonl_sink(path)` → one `mizan verify`-able receipt per line. Without a sink,
set `MIZAN_RECEIPT_LOG` to a path. Use **Ed25519** (`signer=`) for cross-party
audit so verifiers need only a public key.

**Runnable example (no API key needed):** [`examples/openai_agents_receipt.py`](../examples/openai_agents_receipt.py)
invokes a real `FunctionTool` the way the SDK runtime does and writes a verifiable
chain. **Tests:** [`tests/test_adapter_openai_sdk.py`](../tests/test_adapter_openai_sdk.py)
drives the real SDK (success + error paths); skipped automatically when the SDK
isn't installed.

## LangGraph / LangChain

```bash
pip install "mizan[langgraph]"     # adds langgraph + langchain-core; core needs none
```

Compose under LangChain's `@tool`, or wrap existing tools before handing them to
a graph:

```python
from langchain_core.tools import tool
from mizan.adapters.langgraph import receipt_tool, wrap_tools, chain_sink

@tool                                                   # schema from the signature
@receipt_tool(secret="…", sink=chain_sink("receipts.jsonl"))
def get_weather(city: str) -> dict:
    return {"city": city, "temp": 72}

# or wrap a whole list for a ToolNode / create_react_agent:
guarded = wrap_tools(my_tools, secret="…", sink=chain_sink("receipts.jsonl"))
```

Every `.invoke()` appends a signed Receipt v0. Verify with `mizan verify-log` /
`mizan report` as above.

**Runnable example:** [`examples/langgraph_receipt.py`](../examples/langgraph_receipt.py)
(no LLM needed). **Tests:** [`tests/test_adapter_langgraph.py`](../tests/test_adapter_langgraph.py)
drive the real LangChain runtime (compose, wrap, error path); skipped when
LangChain isn't installed.

## CrewAI

Planned next, to the same bar: import-safe adapter, signed Receipt v0 per tool
action, a real smoke test, and clean-install docs.
