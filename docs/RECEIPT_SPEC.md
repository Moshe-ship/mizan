# Mizan Receipt Specification — v0

> **Mizan is a signed evidence layer for agent actions:** it records what the
> agent saw, what policy allowed, what tool ran, what result came back, and
> whether the claim matches execution.

The **Receipt** is that evidence object. One agent turn produces one Receipt —
a portable, signable, replayable record that an auditor can verify *after the
fact* without trusting the agent or the runtime.

This is **v0**: deliberately minimal. It formalizes the object `mizan` already
emits and adds only the fields needed to make a Receipt self-describing,
addressable, time-stamped, and tamper-evident as a single bundle.

- **Status:** draft / public-alpha. Fields may be added (never removed or
  re-typed) within `mizan.receipt/0`. See [Compatibility](#compatibility).
- **Media type:** `application/vnd.mizan.receipt+json`
- **JSON Schema:** [`mizan/schemas/receipt-v0.schema.json`](../mizan/schemas/receipt-v0.schema.json) (shipped as package data)
- **Tooling:** `mizan verify receipt.json` · `mizan diff a.json b.json` (dependency-free)

---

## 1. Design rules (v0)

1. **Hashes, not payloads.** A Receipt stores `sha256` hashes of input/output/
   args/result, plus an *optional* redacted summary — never raw prompt or tool
   data by default. Receipts are safe to ship to an auditor or SIEM.
2. **Append-only stages.** Each stage of the scale (scan → restore → balance →
   classify → constrain → verify) appends one immutable `StageRecord`.
3. **The signature covers everything except itself.** Tamper-evidence over the
   whole bundle — the one thing OpenTelemetry spans do not provide.
4. **Minimal core, extensible detail.** Normalized top-level fields stay small;
   tool-specific richness lives in `stages[].detail`.

## 2. The object

| Field | Type | Required | Notes |
|---|---|---|---|
| `schema_version` | string | yes | Exactly `"mizan.receipt/0"`. |
| `receipt_id` | string | yes | Stable unique id, e.g. `rcpt_<uuid4>`. |
| `created_at` | string | yes | RFC 3339 / ISO 8601 UTC, e.g. `2026-06-01T18:30:00Z`. |
| `subject` | object | yes | `agent_id`, `model`, `run_id`, `tool` — each string-or-null. Identity of the run. |
| `input` | object | yes | `{ "hash": "sha256:…", "summary": string\|null }`. Hash of the agent-visible input. |
| `output` | object | yes | `{ "hash": "sha256:…", "summary": string\|null }`. Hash of the produced output. |
| `decision` | object | yes | `{ "action": "allowed"\|"blocked"\|"escalated", "reason": string }`. The gate verdict for the turn. |
| `execution` | object \| null | yes | What actually ran: `{ "tool", "args_hash", "result_hash", "observed_status" }` (nullable members). `null` if no tool executed. |
| `claim` | object \| null | yes | What the agent *said* it did: `{ "tool", "result_hash" }`. `null` if no claim to check. |
| `verification` | string | yes | `"verified"` \| `"unverified"` \| `"tampered"` \| `"not_applicable"`. Does `claim` match `execution`? |
| `stages` | array | yes | Ordered `StageRecord`s (may be empty). |
| `signature` | object | yes | `{ "algorithm": "HMAC-SHA256", "key_id": string\|null, "value": "<hex>" }`. |

### StageRecord

| Field | Type | Required | Notes |
|---|---|---|---|
| `stage` | string | yes | One of `scan`,`restore`,`balance`,`classify`,`constrain`,`verify`. |
| `tool` | string | yes | Implementing package, e.g. `mcpscan`,`jabr`,`muqabalah`,`qadiya`,`mtg`,`toolproof`. |
| `ok` | boolean | yes | `false` when the stage refused/blocked/failed. |
| `changes` | integer | yes | Count of substantive changes the stage made (≥0). |
| `detail` | object | yes | Tool-specific, JSON-serializable. May be `{}`. |

> `decision.action` is derived from stages: any refusing stage → `blocked`; a
> classify/constrain escalation → `escalated`; otherwise `allowed`.

## 3. Canonical form & signing

The signature is computed over the **canonical JSON** of the entire Receipt
**with the `signature` field removed**. Canonicalization is **RFC 8785 (JSON
Canonicalization Scheme) aligned**, constrained to the receipt value space so a
JS verifier and a Python signer can never disagree:

1. Remove `signature`.
2. **No floats.** Receipts use only objects, arrays, strings, integers,
   booleans, and null. A float in the canonical form is an error (the reference
   implementation raises) — this removes the one real cross-language ambiguity
   (number formatting). Counts like `changes` are integers.
3. Object keys are sorted by Unicode code point. v0 keys are ASCII, so this
   coincides with RFC 8785's UTF-16 code-unit ordering.
4. Serialize as UTF-8 JSON, `ensure_ascii=false`, no insignificant whitespace
   (`separators=(",", ":")`).
5. `value = HEX( HMAC_SHA256(key, canonical_bytes) )`.

Verification recomputes the same canonical form and compares in constant time.
`algorithm` is fixed to `HMAC-SHA256` in v0; `key_id` names the secret used so
a verifier can select the right key. (A future profile may add asymmetric /
keyless signing; v0 is symmetric by design — shared-secret tamper-evidence.)

Hash strings are lowercase hex prefixed by algorithm: `sha256:<64-hex>`.

## 4. OpenTelemetry GenAI mapping

A Receipt is **above** observability, not a replacement for it. Stages map to
OTel GenAI spans; Receipt-specific signal uses the `mizan.*` namespace.

| Receipt field | OTel GenAI attribute / span |
|---|---|
| `subject.agent_id` | `gen_ai.agent.id` |
| `subject.model` | `gen_ai.request.model` |
| `subject.tool` / `execution.tool` | `gen_ai.tool.name` (on `execute_tool` span) |
| one `StageRecord` | a child span `mizan.stage.<stage>` under the run's `invoke_agent` span |
| `signature.value` | `mizan.receipt.signature` (parent span attribute) |
| `signature.key_id` | `mizan.receipt.key_id` |
| `verification` | `mizan.receipt.verification` |

OTel GenAI semconv defines `gen_ai.agent.id/name/version` and
`invoke_agent`/`execute_tool` spans but **no provenance, signing, or
attestation** — the Receipt fills exactly that gap.

## 5. Standards alignment

- **OWASP MCP08 (Lack of Audit & Telemetry)** recommends *OpenTelemetry tracing*
  **+** *cryptographic hashing (HMAC/SHA-256) for log integrity* **+** *append-only
  storage*. A signed Receipt with OTel export implements all three.
- **OWASP MCP03 (Tool Poisoning)** maps to the `scan` stage.

> Scope honestly: many SIEM/observability tools also satisfy MCP08. The
> Receipt's differentiator is being a **portable, self-verifying object**, not
> the act of logging.

## 6. Examples

See [`examples/receipts/`](../examples/receipts/): `passed.json`,
`blocked.json`, `tampered.json`. A `tampered` receipt is one whose `signature`
no longer matches its canonical form — `mizan verify` returns non-zero.

## 7. Compatibility

`schema_version` is `mizan.receipt/<MAJOR>`. Within a major:

- **Allowed (minor):** add new optional fields; add new enum values to
  `verification`/`decision.action` *only if* consumers treat unknown values as
  `unverified`/`escalated` respectively.
- **Breaking (new major):** remove/rename a field, change a type, or change the
  canonical-form/signing rules. A new major gets a new `schema_version`.

Verifiers MUST ignore unknown top-level fields (forward-compatible).

## 8. Conformance

As of **mizan 0.1.6**, `Receipt.to_v0(secret=…)` emits the full v0 document
above, and `mizan verify` / `mizan diff` validate it — both dependency-free.
This is **additive**: `Receipt.to_dict()` is unchanged and still returns the
legacy shape (raw `input`/`output`, `ok`/`blocked_by`, `stages`). A future
major (0.2.0) may make v0 the default output.

| Capability | Status in 0.1.6 |
|---|---|
| `Receipt.to_v0(secret, …)` → signed v0 doc | ✅ `mizan/receipt_v0.py` |
| Hashed `input`/`output` (+ optional `summary`) | ✅ (privacy default: `redact=True`) |
| `schema_version`/`receipt_id`/`created_at`/signature envelope | ✅ |
| `decision`/`verification` derived from stages; `execution`/`claim` from verify stage | ✅ (overridable) |
| `mizan verify` (structural + JCS-canonical HMAC check) | ✅ exit 0/1/2/3/4 |
| `mizan diff` | ✅ |
| Full JSON-Schema validation | ✅ when `jsonschema` is installed; structural check otherwise |
| Legacy `Receipt.to_dict()` / `Receipt.signature()` | ✅ unchanged (additive) |

`mizan verify` exit codes: `0` ok · `1` invalid/schema · `2` tampered ·
`3` unsigned · `4` signed-but-no-secret.
