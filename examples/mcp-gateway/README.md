# `mizan gateway` — a Mizan-guarded MCP proxy

Put Mizan in front of your agent's tools. Every tool call gets **scanned, gated,
signed, and logged** — without changing the agent or the tools.

```
   MCP client  ⇄  mizan gateway  ⇄  your real MCP server
                     │
                     ├─ scans every tool descriptor (mcpscan)
                     ├─ gates every call against an allowlist (qadiya)
                     └─ writes a signed Receipt v0 per action (hash-chained)
```

The gateway speaks the MCP **stdio** transport (newline-delimited JSON-RPC 2.0)
on both sides. It launches your downstream server from the config and relays
everything transparently — except it scans `tools/list`, gates `tools/call`,
blocks disallowed calls *before downstream sees them*, and signs a receipt for
every allowed or blocked action. No MCP SDK dependency.

## Run it

```bash
pip install "mizan[all]"

# from this repo (uses the bundled echo_server.py as the downstream server)
mizan gateway --config examples/mcp-gateway/mcp.json --receipt-log receipts.jsonl
```

Then speak MCP to it on stdin (a real client does this for you):

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"safe_echo","arguments":{"text":"hi"}}}' \
  '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"delete_db","arguments":{}}}' \
| mizan gateway --config examples/mcp-gateway/mcp.json --receipt-log receipts.jsonl
```

You'll see (on stderr): `FLAGGED tool poisoned_tool`, `ALLOWED tools/call
safe_echo`, `BLOCKED tools/call delete_db`. The `delete_db` call **never reaches
downstream** — the gateway answers with an MCP tool error.

## See and verify the evidence

```bash
mizan verify-log receipts.jsonl --secret-env MIZAN_RECEIPT_SECRET   # chain intact, sigs valid
MIZAN_RECEIPT_SECRET=gateway-demo-secret mizan report receipts.jsonl --open   # HTML dashboard
```

## Config (`mcp.json`)

```json
{
  "server": { "command": "python3", "args": ["your_mcp_server.py"], "env": {} },
  "policy": { "allow_tools": ["safe_echo"] },
  "receipt": { "secret": "change-me" }
}
```

- **`server`** — the real downstream MCP server to launch (any command).
- **`policy.allow_tools`** — the allowlist; any tool not listed is **blocked** and
  escalated, never silently run. Omit `policy` to allow all (scan + sign only).
- **`receipt.secret`** — HMAC signing key (or set `MIZAN_RECEIPT_SECRET`, which
  takes precedence). For cross-party audit, use `receipt.ed25519` instead so
  auditors verify with a public key alone.

## What's bundled here

- [`echo_server.py`](echo_server.py) — a tiny real downstream MCP server with
  three tools: `safe_echo` (allowed), `delete_db` (blocked by the policy), and
  `poisoned_tool` (a hidden override directive in its description that the scanner
  flags). Used by the gateway acceptance test (`tests/test_gateway.py`).
- [`mcp.json`](mcp.json) — the config above, wired to `echo_server.py`.
