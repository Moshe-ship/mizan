# Hermes dogfood — reproducible evidence

We don't just publish Mizan; we run it. This folder is the receipt log from a
**real [Hermes](https://github.com/NousResearch/hermes-agent) agent** with Mizan
wired onto its tool-call boundary (the `khwarizmi` plugin). Every prompt was sent
to a live agent; every guarded action left a **signed Receipt v0** in a
hash-chained log. Nothing here is hand-written — check it yourself.

## What's in here

| File | What it is |
|---|---|
| [`prompt.txt`](prompt.txt) | the prompts sent to the live agent |
| [`receipts.jsonl`](receipts.jsonl) | the signed, hash-chained receipt log the agent produced |
| [`verify-output.txt`](verify-output.txt) | real `mizan verify-log` / `mizan verify` output |
| [`report.html`](report.html) | the `mizan report` dashboard for this log |

## What happened

A real agent was asked to run a shell command, to act on a contradictory
instruction, and to email "her". Mizan, sitting in front of the tool calls:

- **blocked** the `terminal` call (not in the allowlist) — *qadiya* tool-gate,
- **refused** the contradictory turn before any tool ran — *muqabalah*,
- **restored** the dropped reference `her → Sara` — *jabr*,

and signed a Receipt v0 for each decision. The log is one unbroken hash chain.

## Verify it yourself

```bash
pip install "mizan[all]"

# 1) the whole log is an intact hash chain, every signature valid
MIZAN_RECEIPT_SECRET=dogfood-demo-secret \
  mizan verify-log receipts.jsonl --secret-env MIZAN_RECEIPT_SECRET
#   ✓ chain intact: 8 link(s), unbroken from genesis
#   ✓ all 8 receipt signatures valid

# 2) render the human-readable dashboard
MIZAN_RECEIPT_SECRET=dogfood-demo-secret \
  mizan report receipts.jsonl --secret-env MIZAN_RECEIPT_SECRET --open

# 3) prove tampering is caught — flip one field and re-verify
python -c "import json; l=open('receipts.jsonl').read().splitlines(); \
d=json.loads(l[-1])['receipt']; d['decision']['action']='allowed'; \
json.dump(d, open('/tmp/forged.json','w'))"
MIZAN_RECEIPT_SECRET=dogfood-demo-secret mizan verify /tmp/forged.json --secret-env MIZAN_RECEIPT_SECRET
#   ✗ signature MISMATCH ... (TAMPERED)   exit 2
```

`dogfood-demo-secret` is a throwaway HMAC key for this public demo. In a real
deployment you'd use a per-environment secret, or **Ed25519** so auditors verify
with a public key alone (`mizan keygen`, then `mizan verify --public-key`).

## Reproduce the run

The plugin that produced this lives at
[`khwarizmi-hermes-plugin`](https://github.com/Moshe-ship/khwarizmi-hermes-plugin).
Install it into a Hermes profile's `~/.hermes/.../plugins/khwarizmi/`, enable it
(`plugins.enabled: [khwarizmi]`), set a `receipt.secret`, and talk to the agent —
the receipt log fills itself.
