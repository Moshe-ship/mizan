# Proposal: a reference pattern for signed agent-action receipts (MCP08)

*Draft for the OWASP MCP Top 10 project. This proposes adding a concrete,
vendor-neutral reference pattern to **MCP08:2025 — Lack of Audit and Telemetry**.
It does not propose any specific tool as a standard.*

## Why

MCP08:2025 already recommends the right primitives — *use OpenTelemetry to trace
requests across the MCP pipeline*, *apply cryptographic hashing (HMAC, SHA-256) to
log files for integrity*, and *append-only storage*. But the control names them
generically, which leaves a gap between "we emit telemetry" and **"we can prove,
after the fact, what a tool actually did and whether the agent's claim about it
was true."** Three things generic logging does not give you:

1. **Verifiable per-action evidence.** Spans prove activity happened; they don't
   carry a tamper-evident record of the observed tool execution. The OpenTelemetry
   GenAI semantic conventions (the recommended tracing) define agent/tool span
   attributes but contain **no provenance, signing, or attestation**.
2. **Claim-vs-execution.** Nothing in the control distinguishes *the agent
   reported a result* from *the tool actually returned that result*.
3. **Third-party verifiability.** Hashing a log file with a shared HMAC secret
   gives a verifier the same key that can forge it — fine for one trust domain,
   weak for cross-party audit.

## Proposed reference pattern: a signed, OTel-aligned action receipt

For each agent tool action, emit a signed **receipt** with four properties.
The point is the *shape*, so any implementation interoperates:

1. **Per-action evidence (OTel-aligned).** Record hashed input/output, the policy
   `decision`, and the observed `execution` (tool name, args hash, result hash,
   status), mapped to OTel GenAI attributes (`gen_ai.agent.id`, `gen_ai.tool.name`,
   …) so it rides existing tracing.
2. **Claim-vs-execution verification.** Record the agent's *claimed* result and a
   verdict comparing it to the *observed* execution (`verified` / `tampered`), so
   "the agent lied about the result" is detectable — and a verifier **recomputes**
   the comparison rather than trusting the receipt's own verdict.
3. **Tamper-evident signature, with an asymmetric option.** HMAC-SHA256 for a
   single trust domain; **Ed25519** (or similar) so an auditor verifies with only
   a **public key** and never holds signing authority. A `key_id` records which
   key signed, making rotation auditable.
4. **Append-only, hash-chained storage.** Chain receipts so each entry commits to
   the prior entry's digest — making edits, insertions, reorders, and middle
   removals tamper-evident. Anchor the head digest/count externally (or use WORM
   media) to also catch tail truncation. This realizes MCP08's *append-only*
   recommendation as a *verifiable sequence*, not just a write mode.

## How it maps to the MCP08 controls

| MCP08 recommends | The pattern adds |
|---|---|
| OpenTelemetry tracing | receipts emit OTel-compatible spans (same pipeline) |
| Cryptographic hashing for integrity | a signature over a **canonical** receipt — per-action, not per-file; HMAC or asymmetric |
| Append-only storage | a **hash chain** that makes the sequence tamper-evident, not only the medium |
| (not covered) | **claim-vs-execution** verification — did the agent lie? |

## Honest scope

This is tamper-**evidence**, not tamper-**prevention**: it makes undetected
editing infeasible, not impossible. It does not address signing-key misuse, real-
time blocking, or storage availability. It is an *audit* control — exactly MCP08's
remit.

## Reference implementation (existence proof, not a requirement)

[Mizan](https://github.com/Moshe-ship/mizan) (open source, on PyPI) implements
this pattern as an existence proof: a frozen
[Receipt v0 JSON Schema](RECEIPT_SPEC.md), a dependency-free `mizan verify`
(integrity + claim-vs-execution), Ed25519 signing with public-key verification,
and a hash-chained append-only log ([AUDIT_STORAGE.md](AUDIT_STORAGE.md)). It is
cited as one way to satisfy the control, not as something MCP08 should mandate.

## Suggested change

Add a short *"Reference pattern — signed action receipts"* subsection under
MCP08's mitigations, describing the four properties above and the OTel GenAI
field alignment, with a note that any conforming receipt shape interoperates.
