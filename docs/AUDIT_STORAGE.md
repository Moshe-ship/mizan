# Audit storage — deployable tamper-evident receipt trails

A Mizan Receipt is signed, so each one is *intact-evident*. For a real audit
trail you also need the **log** to be tamper-evident — no one quietly removed,
reordered, or inserted entries — and the receipts to live somewhere they can't
be silently rewritten. This is the guidance for that.

Three layers, each closing a distinct gap:

| Layer | Proves | How |
|---|---|---|
| **Signature** (per receipt) | this receipt wasn't modified after signing | HMAC-SHA256 or Ed25519 — `mizan verify` |
| **Hash chain** (the sequence) | the log wasn't reordered / truncated / inserted into | `mizan.chain.ReceiptLog` — `mizan verify-log` |
| **Write-once storage** (the medium) | the file itself wasn't rewritten in place | append-only / WORM medium + an external anchor |

## 1. Sign every receipt

For a single trust domain, HMAC is enough. For **third-party audit** use Ed25519
(`pip install "mizan[ed25519]"`): the auditor verifies with the **public key**
only and never holds signing authority. Either way the `key_id` records *which*
key signed, so rotation is auditable. See [RECEIPT_SPEC.md](RECEIPT_SPEC.md).

## 2. Chain the log

Per-receipt signatures don't stop someone with write access from deleting
yesterday's receipt. A hash chain does: each entry commits to the previous
entry's digest, so any removal/reorder/insertion breaks the chain from that
point.

```python
from mizan.chain import ReceiptLog

log = ReceiptLog("audit.jsonl")     # append-only JSONL, one link per line
log.append(receipt_a)               # link 0, prev = genesis
log.append(receipt_b)               # link 1, prev = digest(link 0)
```

```bash
mizan verify-log audit.jsonl                                   # chain integrity
mizan verify-log audit.jsonl --secret-env MIZAN_RECEIPT_SECRET # + every signature (HMAC)
mizan verify-log audit.jsonl --public-key key.json             # + every signature (Ed25519)
```

Exit codes: `0` ok · `1` chain broken · `2` a receipt signature failed.

The log is plain JSONL — each line is `{seq, prev, digest, receipt}` — so it
streams to anything without this library.

## 3. Store it write-once, and anchor the head

A chain only helps if an attacker can't recompute it after editing. Two
controls make that infeasible:

- **Append-only / WORM medium.** Write the JSONL to storage that forbids
  in-place edits: object storage with object-lock / retention (e.g. S3
  Object Lock, GCS retention), an append-only table, or a write-once volume.
- **Anchor the head digest externally.** Periodically publish the current
  `log.head_digest()` somewhere the operator can't quietly rewrite — a second
  party, a transparency log, a timestamping service, or a Mizan receipt of the
  head signed with a *different* key. Anyone can later recompute the chain and
  check it ends at the anchored head, which makes truncation detectable even if
  the whole file is replaced.

## 4. Ship to a SIEM / observability stack

Mizan receipts are OTel-aligned (`mizan.otel`), so the same evidence flows into
normal monitoring **without losing the signature**: the parent span carries
`mizan.receipt.signature` / `mizan.receipt.key_id`. Pattern:

- Emit OTel spans for live dashboards/alerting (search, latency, decision rates).
- **Independently** append the signed receipt to the chained log on write-once
  storage — that, not the SIEM copy, is the authoritative audit trail (a SIEM is
  optimized for query, not for being un-rewritable).
- Reconcile periodically: the count and head digest of the log vs the spans.

## Scope, honestly

This gives tamper-**evidence**, not tamper-**prevention**: it makes undetected
editing infeasible, not impossible. It does not address insider misuse of the
signing key (rotate keys; for Ed25519, distribute and pin public keys), real-time
prevention, or storage availability. HMAC remains shared-secret; for cross-party
trust use Ed25519. The hash chain is SHA-256 over the
[RFC 8785-aligned canonical form](RECEIPT_SPEC.md#3-canonical-form--signing).
