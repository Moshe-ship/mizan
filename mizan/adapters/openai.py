"""OpenAI Agents SDK adapter — a signed Receipt for every tool call.

Wrap a tool function with :func:`receipt_tool`; each invocation hashes the
arguments and result, captures the observed status, and emits a signed
Receipt v0 (see ``docs/RECEIPT_SPEC.md``). Compose it *under* the SDK's
``@function_tool`` so the SDK still derives the schema from the original
signature::

    from agents import function_tool
    from mizan.adapters.openai import receipt_tool

    @function_tool
    @receipt_tool(secret="…", key_id="local")
    def get_weather(city: str) -> dict:
        return {"city": city, "temp": 72}

This module imports neither ``openai`` nor ``agents`` — it works on any
callable. ``pip install "mizan[openai]"`` adds the SDK for end-to-end use.
"""

from __future__ import annotations

import functools
import inspect
import json
import os
from typing import Any, Callable, Optional

from mizan import receipt_v0
from mizan.receipt import Receipt, StageRecord

Sink = Callable[[dict], None]


# --------------------------------------------------------------------------- #
# Serialization helpers (lenient — used only to HASH; floats are fine here
# because only the resulting hash string ever enters the receipt).
# --------------------------------------------------------------------------- #
def _jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    for attr in ("model_dump", "dict"):  # pydantic v2 / v1
        method = getattr(obj, attr, None)
        if callable(method):
            try:
                return _jsonable(method())
            except Exception:  # noqa: BLE001
                pass
    return repr(obj)


def _stable_json(obj: Any) -> str:
    return json.dumps(_jsonable(obj), sort_keys=True, ensure_ascii=False, default=str)


def _looks_like_context(obj: Any) -> bool:
    """Heuristic for the SDK's RunContextWrapper (passed as the first arg)."""
    return type(obj).__name__.endswith("ContextWrapper") or hasattr(obj, "context")


def _current_trace_id() -> Optional[str]:
    """Active OpenTelemetry trace id (hex), if OTel is installed and recording."""
    try:
        from opentelemetry import trace

        ctx = trace.get_current_span().get_span_context()
        if ctx and ctx.trace_id:
            return format(ctx.trace_id, "032x")
    except Exception:  # noqa: BLE001
        return None
    return None


def jsonl_sink(path: str) -> Sink:
    """A sink that appends each receipt to a JSONL file."""
    def _sink(doc: dict) -> None:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, ensure_ascii=False) + "\n")
    return _sink


def _emit(doc: dict, sink: Optional[Sink]) -> None:
    if sink is not None:
        sink(doc)
        return
    path = os.environ.get("MIZAN_RECEIPT_LOG")
    if path:
        jsonl_sink(path)(doc)


# --------------------------------------------------------------------------- #
# The decorator
# --------------------------------------------------------------------------- #
def receipt_tool(
    func: Optional[Callable] = None,
    *,
    secret: Optional[str] = None,
    key_id: Optional[str] = None,
    sink: Optional[Sink] = None,
    redact: bool = True,
    agent_id: Optional[str] = None,
    model: Optional[str] = None,
    run_id: Optional[str] = None,
    tool_name: Optional[str] = None,
    skip_context: bool = True,
):
    """Wrap a tool so every call emits a signed Receipt v0.

    The receipt records the tool name, an args hash, a result hash, and the
    observed status (``ok`` / ``error``). It is delivered to ``sink`` if given,
    else appended to ``$MIZAN_RECEIPT_LOG`` if set; the most recent receipt is
    always available as ``wrapped.last_receipt``.

    ``run_id`` falls back to the active OpenTelemetry trace id when available.
    The leading ``RunContextWrapper`` argument (if any) is excluded from the
    args hash by default (``skip_context``) — it is framework plumbing, not a
    tool input.
    """

    def decorate(fn: Callable) -> Callable:
        name = tool_name or getattr(fn, "__name__", "tool")

        def _hash_args(args: tuple, kwargs: dict) -> tuple[str, str]:
            hashed = list(args)
            if skip_context and hashed and _looks_like_context(hashed[0]):
                hashed = hashed[1:]
            blob = _stable_json({"args": hashed, "kwargs": kwargs})
            return blob, receipt_v0.hash_text(blob)

        def _finish(args_blob: str, args_hash: str, result: Any, status: str, error: Optional[str]) -> dict:
            ok = status == "ok"
            result_blob = _stable_json(result) if ok else ""
            result_hash = receipt_v0.hash_text(result_blob) if ok else None
            detail: dict[str, Any] = {"observed_status": status}
            if error:
                detail["error"] = error
            r = Receipt(
                input=args_blob,
                output=result_blob,
                stages=(StageRecord("verify", name, ok=ok, detail=detail),),
            )
            doc = r.to_v0(
                secret=secret, key_id=key_id, redact=redact, tool=name,
                agent_id=agent_id, model=model, run_id=run_id or _current_trace_id(),
                execution={
                    "tool": name, "args_hash": args_hash,
                    "result_hash": result_hash, "observed_status": status,
                },
                claim=None, verification="not_applicable",
            )
            return doc

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def awrapper(*args: Any, **kwargs: Any) -> Any:
                args_blob, args_hash = _hash_args(args, kwargs)
                status, error, result = "ok", None, None
                try:
                    result = await fn(*args, **kwargs)
                    return result
                except Exception as exc:  # noqa: BLE001
                    status, error = "error", type(exc).__name__
                    raise
                finally:
                    doc = _finish(args_blob, args_hash, result, status, error)
                    awrapper.last_receipt = doc
                    _emit(doc, sink)

            awrapper.last_receipt = None  # type: ignore[attr-defined]
            return awrapper

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            args_blob, args_hash = _hash_args(args, kwargs)
            status, error, result = "ok", None, None
            try:
                result = fn(*args, **kwargs)
                return result
            except Exception as exc:  # noqa: BLE001
                status, error = "error", type(exc).__name__
                raise
            finally:
                doc = _finish(args_blob, args_hash, result, status, error)
                wrapper.last_receipt = doc
                _emit(doc, sink)

        wrapper.last_receipt = None  # type: ignore[attr-defined]
        return wrapper

    return decorate(func) if callable(func) else decorate
