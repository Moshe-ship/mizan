"""CrewAI adapter — a signed Receipt for every tool call.

Two ways to use it, both import-safe (the core imports no CrewAI):

1. **Compose** under CrewAI's ``@tool`` so the schema is still derived from the
   original signature::

       from crewai.tools import tool
       from mizan.adapters.crewai import receipt_tool, chain_sink

       @tool("get_weather")
       @receipt_tool(secret="…", sink=chain_sink("receipts.jsonl"))
       def get_weather(city: str) -> dict:
           return {"city": city, "temp": 72}

2. **Wrap existing tools** before handing them to an Agent/Crew::

       from mizan.adapters.crewai import wrap_tools, chain_sink
       guarded = wrap_tools(my_tools, secret="…", sink=chain_sink("receipts.jsonl"))

Each ``.run()`` appends a signed Receipt v0 (hashed args/result, observed
status). ``pip install "mizan[crewai]"`` adds CrewAI for end-to-end use; verify
with ``mizan verify-log`` / ``mizan report``.

Note: CrewAI pulls heavy native deps (e.g. ``tiktoken``) that currently build on
Python 3.11/3.12. The adapter itself needs none of that — it only touches the
tool object you pass in.
"""

from __future__ import annotations

from typing import Any, Optional

# Framework-agnostic decorator + sinks — no CrewAI import here.
from mizan.adapters.openai import Sink, chain_sink, jsonl_sink, receipt_tool

__all__ = ["receipt_tool", "chain_sink", "jsonl_sink", "wrap_tool", "wrap_tools"]


def wrap_tool(tool: Any, *, secret: Optional[str] = None, key_id: Optional[str] = None,
              sink: Optional[Sink] = None, agent_id: Optional[str] = None,
              model: Optional[str] = None, run_id: Optional[str] = None,
              redact: bool = True) -> Any:
    """Return a copy of a CrewAI ``@tool`` whose function emits a signed Receipt
    v0 on every ``.run()``. Name, description, and schema are preserved.

    Works on function-backed tools (the ``@tool`` decorator). Needs no CrewAI
    import — it calls ``model_copy`` on the tool you pass in."""
    func = getattr(tool, "func", None)
    if func is None:
        raise TypeError(
            f"{tool!r} has no .func — wrap_tool supports @tool function tools; "
            "for a BaseTool subclass, compose receipt_tool inside its _run instead.")
    receipted = receipt_tool(
        secret=secret, key_id=key_id, sink=sink, agent_id=agent_id,
        model=model, run_id=run_id, redact=redact,
        tool_name=getattr(tool, "name", None),
    )(func)
    if hasattr(tool, "model_copy"):           # pydantic v2 (current CrewAI)
        return tool.model_copy(update={"func": receipted})
    if hasattr(tool, "copy"):                 # pydantic v1 fallback
        return tool.copy(update={"func": receipted})
    tool.func = receipted                     # last resort: mutate in place
    return tool


def wrap_tools(tools: list, **kwargs: Any) -> list:
    """Wrap a list of CrewAI tools before handing them to an Agent/Crew."""
    return [wrap_tool(t, **kwargs) for t in tools]
