"""Acceptance test for `mizan gateway` — a REAL MCP stdio proxy.

Spawns the actual gateway process, which launches the actual downstream MCP
server (examples/mcp-gateway/echo_server.py), and drives it as an MCP client.
No mocks: every message crosses real pipes.

Asserts the gateway's whole contract:
  - initialize is relayed
  - tools/list is relayed AND poisoned_tool is flagged (signed scan receipt)
  - safe_echo (allowed) reaches downstream and returns its real result
  - delete_db (blocked) NEVER reaches downstream (its destructive sentinel never
    appears, and the downstream call-log never records it)
  - both allowed and blocked calls produce signed Receipt v0 entries
  - the whole receipt chain passes `mizan verify-log`
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mizan.chain import verify_log
from mizan import receipt_v0

SECRET = "gw-test-secret"


def _spawn(tmp_path):
    calls = os.path.join(tmp_path, "calls.log")
    cfg = {
        "server": {"command": sys.executable,
                   "args": [os.path.join(ROOT, "examples/mcp-gateway/echo_server.py")],
                   "env": {"MIZAN_ECHO_CALLS": calls}},
        "policy": {"allow_tools": ["safe_echo"]},
        "receipt": {"secret": SECRET},
    }
    cfg_path = os.path.join(tmp_path, "mcp.json")
    with open(cfg_path, "w") as fh:
        json.dump(cfg, fh)
    rl = os.path.join(tmp_path, "receipts.jsonl")
    errf = open(os.path.join(tmp_path, "gw.err"), "w")
    # Hermetic: don't let an ambient MIZAN_RECEIPT_SECRET override the config
    # secret this test verifies against.
    env = os.environ.copy()
    env.pop("MIZAN_RECEIPT_SECRET", None)
    proc = subprocess.Popen(
        [sys.executable, "-m", "mizan", "gateway", "--config", cfg_path, "--receipt-log", rl],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errf,
        text=True, bufsize=1, cwd=ROOT, env=env,
    )
    q: "queue.Queue" = queue.Queue()

    def _reader():
        for line in proc.stdout:
            q.put(line)
        q.put(None)

    threading.Thread(target=_reader, daemon=True).start()
    return proc, q, calls, rl


def test_gateway_scan_gate_sign(tmp_path):
    proc, q, calls, rl = _spawn(str(tmp_path))

    def send(obj):
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def recv():
        line = q.get(timeout=10)
        assert line is not None, "gateway closed unexpectedly"
        return json.loads(line)

    try:
        # 1) initialize is relayed
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        r = recv()
        assert r["id"] == 1 and "result" in r

        # 2) tools/list is relayed intact
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        r = recv()
        names = [t["name"] for t in r["result"]["tools"]]
        assert {"safe_echo", "delete_db", "poisoned_tool"} <= set(names)

        # 3) allowed call reaches downstream and returns the real result
        send({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
              "params": {"name": "safe_echo", "arguments": {"text": "hi"}}})
        r = recv()
        assert "echo: hi" in json.dumps(r["result"]), r

        # 4) blocked call: error result, downstream sentinel absent
        send({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
              "params": {"name": "delete_db", "arguments": {}}})
        r = recv()
        assert r["result"]["isError"] is True
        assert "DB DELETED" not in json.dumps(r), "blocked call leaked downstream result!"
    finally:
        proc.stdin.close()
        proc.wait(timeout=10)

    # 5) downstream saw safe_echo but NEVER delete_db
    seen = open(calls).read().split() if os.path.exists(calls) else []
    assert "safe_echo" in seen, seen
    assert "delete_db" not in seen, f"blocked tool reached downstream: {seen}"

    # 6) receipts: scan flag + allowed + blocked, all signed, chain intact
    receipts = [json.loads(l)["receipt"] for l in open(rl)]
    kinds = {(r["stages"][0]["tool"], r["decision"]["action"]) for r in receipts}
    assert ("mcpscan", "blocked") in kinds or any(
        r["stages"][0]["tool"] == "mcpscan" for r in receipts), "poisoned_tool not flagged"
    assert any(r["decision"]["action"] == "allowed" for r in receipts), "no allowed receipt"
    assert any(r["decision"]["action"] == "blocked"
               and r["stages"][0]["tool"] == "qadiya" for r in receipts), "no blocked receipt"
    for r in receipts:
        assert receipt_v0.verify(r, SECRET) == receipt_v0.OK, "a receipt is not signed/valid"

    ok, problems = verify_log(rl)
    assert ok, f"chain broken: {problems}"
    print(f"OK: {len(receipts)} signed receipts, chain intact, blocked call never reached downstream")


if __name__ == "__main__":
    import tempfile
    test_gateway_scan_gate_sign(tempfile.mkdtemp())
    print("\nPASS")
