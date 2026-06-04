"""LangGraph / LangChain adapter — a signed Receipt for every tool call.

Two ways to use it, both import-safe (the core imports no LangChain):

1. **Compose** under LangChain's ``@tool`` so the schema is still derived from
   the original signature::

       from langchain_core.tools import tool
       from mizan.adapters.langgraph import receipt_tool, chain_sink

       @tool
       @receipt_tool(secret="…", sink=chain_sink("receipts.jsonl"))
       def get_weather(city: str) -> dict:
           return {"city": city, "temp": 72}

2. **Wrap existing tools** (idiomatic when you hand a list to ``ToolNode`` /
   ``create_react_agent``)::

       from mizan.adapters.langgraph import wrap_tools, chain_sink
       guarded = wrap_tools(my_tools, secret="…", sink=chain_sink("receipts.jsonl"))

Each ``.invoke()`` appends a signed Receipt v0 (hashed args/result, observed
status). ``pip install "mizan[langgraph]"`` adds LangChain for end-to-end use;
verify with ``mizan verify-log`` / ``mizan report``.
"""

from __future__ import annotations

from typing import Any, Optional

# Re-export the framework-agnostic decorator + sinks (no LangChain import here).
from mizan.adapters.openai import Sink, chain_sink, jsonl_sink, receipt_tool

__all__ = ["receipt_tool", "chain_sink", "jsonl_sink", "wrap_tool", "wrap_tools"]


def wrap_tool(tool: Any, *, secret: Optional[str] = None, key_id: Optional[str] = None,
              sink: Optional[Sink] = None, agent_id: Optional[str] = None,
              model: Optional[str] = None, run_id: Optional[str] = None,
              redact: bool = True) -> Any:
    """Return a copy of an existing LangChain tool whose function emits a signed
    Receipt v0 on every ``.invoke()``. Schema, name, and description are kept."""
    from langchain_core.tools import StructuredTool

    func = getattr(tool, "func", None)
    if func is None:
        raise TypeError(f"{tool!r} has no .func to wrap (async-only tools are not yet supported)")
    receipted = receipt_tool(
        secret=secret, key_id=key_id, sink=sink, agent_id=agent_id,
        model=model, run_id=run_id, redact=redact, tool_name=tool.name,
    )(func)
    return StructuredTool.from_function(
        receipted, name=tool.name, description=tool.description,
        args_schema=getattr(tool, "args_schema", None),
    )


def wrap_tools(tools: list, **kwargs: Any) -> list:
    """Wrap a list of tools (e.g. before handing them to a LangGraph ToolNode)."""
    return [wrap_tool(t, **kwargs) for t in tools]
