"""``mizan gateway`` — a Mizan-guarded MCP stdio proxy.

    mizan gateway --config mcp.json --receipt-log receipts.jsonl

The gateway speaks the MCP stdio transport (newline-delimited JSON-RPC 2.0) on
*both* sides: it is an MCP **server** to its client (over its own stdin/stdout)
and an MCP **client** to a real downstream server it launches from the config.
It relays messages transparently except where it earns its keep:

  * ``tools/list`` responses — every tool descriptor is scanned with
    ``mizan.mcpscan``; poisoned ones are flagged (a signed scan receipt).
  * ``tools/call`` requests — run through a ``qadiya`` allow-gate. **Blocked
    calls never reach downstream** (the gateway answers with an MCP tool error);
    **allowed calls** are forwarded, their real result captured, and a signed
    Receipt v0 emitted. Both outcomes append to a hash-chained ``ReceiptLog``.

No MCP SDK dependency — raw JSON-RPC, to keep Mizan's zero-dep posture. IDs,
errors, subprocess lifecycle, downstream stderr, and malformed JSON are all
handled without crashing the relay.

Config (``mcp.json``)::

    {
      "server": {"command": "python3", "args": ["server.py"], "env": {}},
      "policy": {"allow_tools": ["safe_echo"]},
      "receipt": {"secret": "..."}          // or pass --secret-env
    }
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from typing import Any, Optional

from mizan import receipt_v0
from mizan.chain import ReceiptLog
from mizan.mcpscan import scan_tool
from mizan.receipt import Receipt, StageRecord

try:
    from mizan import ToolGate, equals_constraint
    _GATE_OK = True
except Exception:  # noqa: BLE001 — gate is optional; absence => pass-through allow
    _GATE_OK = False


# --------------------------------------------------------------------------- #
# Receipt builders — one Receipt per guarded action.
# --------------------------------------------------------------------------- #
def _args_in(name: str, args: Any) -> str:
    return name + "(" + json.dumps(args or {}, sort_keys=True, ensure_ascii=False,
                                   default=str) + ")"


def _blocked_receipt(name: str, args: Any, reason: str) -> Receipt:
    return Receipt(_args_in(name, args), "blocked", stages=(
        StageRecord(stage="classify", tool="qadiya", ok=False,
                    detail={"tool": name, "reason": reason}),))


def _allowed_receipt(name: str, args: Any, result: Any) -> Receipt:
    return Receipt(_args_in(name, args), "allowed", stages=(
        StageRecord(stage="classify", tool="qadiya", ok=True, detail={
            "tool": name,
            "execution": {
                "tool": name,
                "args_hash": receipt_v0.hash_value(args or {}),
                "result_hash": receipt_v0.hash_value(result),
                "status": "ok",
            },
        }),))


def _scan_receipt(tool: dict, findings: list) -> Receipt:
    return Receipt(f"tool:{tool.get('name', '')}", "flagged", stages=(
        StageRecord(stage="scan", tool="mcpscan", ok=False, changes=len(findings),
                    detail={"tool": tool.get("name"), "findings": findings}),))


# --------------------------------------------------------------------------- #
# Gateway
# --------------------------------------------------------------------------- #
class Gateway:
    def __init__(self, config: dict, receipt_log_path: str, *,
                 secret: Optional[str] = None, signer: Any = None,
                 client_in=None, client_out=None, diag=None) -> None:
        self.cfg = config
        self.secret = secret
        self.signer = signer
        self.run_id = "gw_" + uuid.uuid4().hex[:12]
        self.log = ReceiptLog(receipt_log_path)
        self._loglock = threading.Lock()
        self._outlock = threading.Lock()
        self._pending: dict[str, tuple[str, Any]] = {}
        self._pendlock = threading.Lock()

        self.client_in = client_in or sys.stdin
        self.client_out = client_out or sys.stdout
        self.diag = diag or sys.stderr

        # allow-gate from policy.allow_tools (absent => everything allowed)
        self.gate = None
        allow = (config.get("policy") or {}).get("allow_tools") or []
        if allow and _GATE_OK:
            c = equals_constraint("tool", "tool_name", [str(t) for t in allow])
            self.gate = ToolGate([c], [f"tool={t}" for t in allow])

        # launch the real downstream MCP server
        srv = config["server"]
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in (srv.get("env") or {}).items()})
        self.proc = subprocess.Popen(
            [srv["command"], *[str(a) for a in srv.get("args", [])]],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, text=True, bufsize=1,
        )

    # -- io helpers -------------------------------------------------------- #
    def _diag(self, msg: str) -> None:
        try:
            self.diag.write(f"[gateway] {msg}\n")
            self.diag.flush()
        except Exception:  # noqa: BLE001
            pass

    def _to_client(self, msg: dict) -> None:
        with self._outlock:
            self.client_out.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.client_out.flush()

    def _to_server(self, raw: str) -> None:
        self.proc.stdin.write(raw + "\n")
        self.proc.stdin.flush()

    @staticmethod
    def _idkey(mid: Any) -> str:
        return json.dumps(mid, sort_keys=True)

    def _emit(self, receipt: Receipt, *, tool: Optional[str] = None) -> None:
        try:
            doc = receipt.to_v0(secret=self.secret, signer=self.signer,
                                agent_id="mizan-gateway", run_id=self.run_id, tool=tool)
            with self._loglock:
                self.log.append(doc)
        except Exception as exc:  # noqa: BLE001
            self._diag(f"receipt emit failed: {exc}")

    # -- client -> downstream --------------------------------------------- #
    def handle_client(self, msg: dict, raw: str) -> None:
        if msg.get("method") == "tools/call":
            params = msg.get("params") or {}
            name = params.get("name", "")
            args = params.get("arguments") or {}
            if self.gate is not None:
                d = self.gate.check({"tool_name": name, "args": args})
                if not d.allowed:
                    self._emit(_blocked_receipt(name, args, d.reason), tool=name)
                    self._to_client({
                        "jsonrpc": "2.0", "id": msg.get("id"),
                        "result": {"isError": True, "content": [{
                            "type": "text",
                            "text": f"mizan-gateway blocked '{name}': {d.reason}",
                        }]},
                    })
                    self._diag(f"BLOCKED tools/call {name} ({d.reason})")
                    return
            with self._pendlock:
                self._pending[self._idkey(msg.get("id"))] = (name, args)
            self._to_server(raw)
            return
        self._to_server(raw)

    # -- downstream -> client --------------------------------------------- #
    def handle_server(self, msg: dict, raw: str) -> None:
        res = msg.get("result")
        if isinstance(res, dict) and isinstance(res.get("tools"), list):
            for tool in res["tools"]:
                if not isinstance(tool, dict):
                    continue
                sres = scan_tool(tool)
                if sres.findings:
                    findings = [f.to_dict() for f in sres.findings]
                    self._emit(_scan_receipt(tool, findings), tool=tool.get("name"))
                    sev = max((f.get("severity", "") for f in findings), default="")
                    self._diag(f"FLAGGED tool {tool.get('name')}: "
                               f"{len(findings)} finding(s) [{sev}]")

        with self._pendlock:
            pend = self._pending.pop(self._idkey(msg.get("id")), None)
        if pend is not None:
            name, args = pend
            self._emit(_allowed_receipt(name, args, res), tool=name)
            self._diag(f"ALLOWED tools/call {name} -> signed receipt")

        with self._outlock:
            self.client_out.write(raw + "\n")
            self.client_out.flush()

    # -- pumps ------------------------------------------------------------- #
    def _pump_server(self) -> None:
        for line in self.proc.stdout:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                self._diag("malformed downstream JSON — forwarding raw")
                with self._outlock:
                    self.client_out.write(line + "\n")
                    self.client_out.flush()
                continue
            try:
                self.handle_server(msg, line)
            except Exception as exc:  # noqa: BLE001
                self._diag(f"downstream handler error: {exc}")

    def _pump_stderr(self) -> None:
        for line in self.proc.stderr:
            try:
                self.diag.write("[downstream] " + line)
                self.diag.flush()
            except Exception:  # noqa: BLE001
                pass

    def run(self) -> int:
        threading.Thread(target=self._pump_stderr, daemon=True).start()
        self._srv_thread = threading.Thread(target=self._pump_server, daemon=True)
        self._srv_thread.start()
        try:
            for line in self.client_in:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    self._diag("malformed client JSON — forwarding raw")
                    self._to_server(line)
                    continue
                try:
                    self.handle_client(msg, line)
                except Exception as exc:  # noqa: BLE001
                    self._diag(f"client handler error: {exc}")
        finally:
            self._shutdown()
        return 0

    def _shutdown(self) -> None:
        # Tell downstream we're done; let it finish any buffered requests and
        # exit on its own so the pump can drain the final responses/receipts.
        try:
            self.proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except Exception:  # noqa: BLE001
                self.proc.kill()
        except Exception:  # noqa: BLE001
            pass
        # join the server pump so the last receipts are flushed before we exit
        srv = getattr(self, "_srv_thread", None)
        if srv is not None:
            srv.join(timeout=5)


def cmd_gateway(args: Any) -> int:
    try:
        with open(args.config, "r", encoding="utf-8") as fh:
            config = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"✗ cannot read config {args.config}: {exc}", file=sys.stderr)
        return 1
    if "server" not in config or "command" not in (config.get("server") or {}):
        print("✗ config needs server.command (the downstream MCP server)", file=sys.stderr)
        return 1

    secret = os.environ.get(getattr(args, "secret_env", "") or "") or \
        (config.get("receipt") or {}).get("secret")
    signer = None
    ed = (config.get("receipt") or {}).get("ed25519") or {}
    if ed.get("private_key"):
        from mizan.signing import Ed25519Signer
        signer = Ed25519Signer(ed["private_key"], key_id=ed.get("key_id"))

    gw = Gateway(config, args.receipt_log, secret=secret, signer=signer)
    gw._diag(f"up — run_id={gw.run_id} · gate={'on' if gw.gate else 'off'} · "
             f"signing={'ed25519' if signer else ('hmac' if secret else 'unsigned')}")
    return gw.run()
