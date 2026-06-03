# Mizan: signed action evidence for AI agents

*A public-alpha, Arabic-first reliability layer that gives every agent tool call
a signed, verifiable receipt.*

---

AI agents now read context, choose tools, fill arguments, call them, and report
back — mostly unsupervised. The question almost no stack answers is the boring,
load-bearing one:

> **Can you prove, after the fact, what the agent saw, what policy allowed, what
> tool actually ran, and whether its claim about the result is true?**

Logs don't prove it (they can be edited). Observability spans don't prove it
(OpenTelemetry has no signing). Guardrails block some bad inputs but leave no
verifiable trail. **Mizan** is the missing layer: a signed *evidence* object for
agent actions.

`pip install mizan` — it's [on PyPI](https://pypi.org/project/mizan/), MIT-licensed
(the `mtg-guards` primitive is Apache-2.0), and the whole stack is published with
token-free [Trusted Publishing + digital attestations](SUPPLY_CHAIN.md).

## The thesis

Agents need a *scale* before autonomy. Mizan models reliability as six staged
operations, each of which appends to one weighable record:

```
scan → restore → balance → classify → constrain → verify → one signed Receipt
```

- **scan** — inspect the MCP tool surface for poisoning (multilingual)
- **restore / balance** — undo prompt-context damage, catch contradictions (fail-loud)
- **classify / constrain** — gate the tool call, constrain its arguments
- **verify** — check the agent's claim against what actually executed
- **→ Receipt** — a signed, portable record an auditor can replay

The **Receipt is the product**. Everything else feeds it.

## The whole thing in one command

```bash
git clone https://github.com/Moshe-ship/mizan && cd mizan
pip install "mizan[all]"
python examples/full_pipeline_demo.py     # the example + corpus live in the repo
```

A poisoned MCP tool, an Arabic request, a transliterated argument, and a lying
agent — Mizan flags the descriptor (BiDi), catches the contradiction, blocks the
transliteration, rejects the fake claim, and emits **one signed Receipt** that
`mizan verify` passes (and a tamper fails). Eight readable steps, one file.

## The Receipt — and how far "signed" goes

```bash
mizan verify receipt.json --secret-env MIZAN_RECEIPT_SECRET   # exit 0 / 2 tampered
```

A Receipt v0 ([spec + JSON Schema](RECEIPT_SPEC.md)) records hashed input/output,
the policy `decision`, the observed `execution`, the agent's `claim`, and a
signature envelope. `mizan verify` is **dependency-free** and does three real things:

1. **Integrity** — the receipt wasn't modified after signing.
2. **Claim vs execution** — it *recomputes* whether the agent's claim matches what
   ran. A receipt can't hide a lie behind its own label, and a signer can't forge
   a `verified` verdict. (`exit 5` when the agent lied.)
3. **Asymmetric trust** — sign with **Ed25519** (`pip install "mizan[ed25519]"`)
   and an auditor verifies with only the **public key** — verification never
   hands out signing authority. `mizan keygen`, then `mizan verify --public-key`.

For a deployable trail, append receipts to a **hash-chained, append-only log**
(`mizan.chain.ReceiptLog`): signatures prove each receipt is intact; the chain
makes edits, insertions, reorders, and middle removals tamper-evident. (Tail
truncation needs an external anchor — `mizan verify-log --expect-head/--expect-count`.
See [AUDIT_STORAGE.md](AUDIT_STORAGE.md).)

It emits **OpenTelemetry-compatible spans** too, so the same evidence flows into
normal monitoring — adding the tamper-evident signature OTel itself doesn't provide.

## The scanner, measured honestly

`mizan.mcpscan` is a multilingual MCP tool-poisoning scanner. It runs from a bare
`pip install mizan` (vendored detectors, no deps) and inspects tool descriptors
for BiDi/Unicode overrides, invisible/zero-width, homoglyphs (incl. fullwidth),
Arabizi, Arabic/English code-switch directives, and semantic exfiltration.

The numbers are [reproducible and per-category](MCP_POISONING_BENCHMARK.md), and
they name their own misses:

- **consistency** (known patterns): **25/25**
- **held-out adversarial** (fresh variants): **16/16**
- **clean false-positive** set: **0 hard false positives**

Two honest framings I won't blur:

- Generic English/Unicode scanners and the OWASP cheat sheet already cover BiDi
  and homoglyphs. **Mizan did not invent Unicode detection.** Its measured edge
  is the **Arabic layer** — Arabizi, code-switch, and the Arabic side of semantic
  exfiltration — categories where Mizan's Arabic-specific rules are designed to go deeper.
- It's **audit/warn-ready, not default-block**. No competitor numbers are claimed:
  the closest tool (Invariant's `mcp-scan`, now Snyk's `snyk-agent-scan`) needs a
  Snyk account + cloud and scans live servers, not raw descriptors, so a clean
  key-free head-to-head isn't something we've run.

This connects to **OWASP MCP Top 10 (2025)**: MCP03 (Tool Poisoning) maps to the
scanner; **MCP08 (Lack of Audit & Telemetry)** recommends exactly *OpenTelemetry
+ cryptographic hashing + append-only storage* — which the signed, chained,
OTel-aligned Receipt is designed to support.

## How it's built (the boring trust work)

- **Token-free publishing**: every package (mizan + 5 standalone primitives)
  ships via PyPI Trusted Publishing (OIDC); each wheel and sdist carries **PEP 740
  attestations** — verify provenance yourself ([how](SUPPLY_CHAIN.md)).
- **Real CI** on every repo (live badges, not static claims); a release gate that
  fails unless the version, both files, provenance, and an install smoke all pass.
- **Protected repos**: required CI on PRs, no force-push/deletion, immutable tags.

## Honest limits (this is public alpha)

- **Not a "fully secure" product.** It's hardened public-alpha: installable,
  attested, token-free, with verifiable receipts. Repository governance and an
  external benchmark reproduction are still maturing.
- The hash chain is tamper-**evidence**, not prevention.
- HMAC is shared-secret (fine for internal logs); use Ed25519 for cross-party audit.
- The scanner is a diagnostic, tuned Arabic-first; recall on genuinely novel
  attacks is measured, not perfect.

## Try it

```bash
git clone https://github.com/Moshe-ship/mizan && cd mizan
pip install "mizan[all]"
python examples/full_pipeline_demo.py     # the example + corpus live in the repo
```

- PyPI: <https://pypi.org/project/mizan/>
- Spec: [RECEIPT_SPEC.md](RECEIPT_SPEC.md) · Benchmark: [MCP_POISONING_BENCHMARK.md](MCP_POISONING_BENCHMARK.md)
- Supply chain: [SUPPLY_CHAIN.md](SUPPLY_CHAIN.md) · Audit storage: [AUDIT_STORAGE.md](AUDIT_STORAGE.md)

If the idea resonates — *agents should not act until their inputs, tool choices,
arguments, and claimed executions can be weighed* — the most useful thing you can
do is **check us**: [REPRODUCE.md](REPRODUCE.md) reproduces every claim (benchmark,
tests, provenance, verifiable receipts) in a few commands. Tell us where it's wrong.
