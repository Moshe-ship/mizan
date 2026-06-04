# Changelog

All notable changes to `mizan` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
semantic versioning (pre-1.0: minor = features, patch = fixes/hardening).

## [0.1.22] — 2026-06-04

### Added
- **`mizan scan <tools.json>`** — a top-level subcommand over the multilingual
  MCP poisoning detectors (BiDi, invisible, homoglyph, Arabizi, code-switch,
  semantic exfil, override), with `--mode audit|warn|block` and an optional
  `--receipt-log` that emits a signed Receipt v0 per scanned tool.
- **`--arabic` mode** — separates **Arabic-specific** risk (Arabizi, Arabic/
  English code-switching, transliteration, Arabic semantic exfil) from
  **generic** Unicode/tool-poisoning risk (BiDi, invisible, homoglyph,
  override), reporting `arabic_risk` and `generic_risk` per tool. Adds an
  Arabic-only **transliteration** check (`R-TRANSLIT-001`) for romanized Arabic
  directives in pure Latin script that English-keyword and mixed-script
  code-switch rules both miss. Plain and `--arabic` produce different,
  assertable output. Arabic mode *separates* Arabic-specific from generic risk;
  it does not claim to replace a generic scanner.
- **`examples/arabic-scan/`** — a one-tool-per-risk-class fixture and README.

## [0.1.21] — 2026-06-03

### Added
- **`mizan gateway --config mcp.json --receipt-log receipts.jsonl`** — a
  Mizan-guarded **MCP stdio proxy**. Launches a downstream MCP server from
  config and relays JSON-RPC transparently (no MCP SDK dependency), while:
  scanning every `tools/list` descriptor (`mcpscan`, flags poisoning); gating
  every `tools/call` against a `policy.allow_tools` allowlist — **blocked calls
  never reach downstream** (the gateway returns an MCP tool error); forwarding
  allowed calls and capturing the real result; and emitting a **signed Receipt
  v0** for both outcomes into a hash-chained log (`mizan verify-log` /
  `mizan report` work on it). Handles ids, errors, subprocess lifecycle,
  downstream stderr, malformed JSON, and graceful drain-on-shutdown.
- **`examples/mcp-gateway/`** — a real downstream server (`echo_server.py`:
  `safe_echo`/`delete_db`/`poisoned_tool`), `mcp.json`, and a README. The
  acceptance test (`tests/test_gateway.py`) drives the real gateway + real
  server end-to-end (no mocks).

### Scope
- The gateway guards **one downstream stdio MCP server** per config — a real
  single-server guarded proxy, not a multi-server router. Multi-server configs,
  per-tool policies, and OTel export are planned for a later version.

## [0.1.20] — 2026-06-03

### Added
- **`mizan report <log>`** — render a self-contained HTML dashboard from a
  signed receipt log: per action shows session, tool, decision (allowed/blocked),
  reason, signature validity, claim verdict, and a chain-integrity banner.
  Stdlib-only (no JS/assets). `--secret-env`/`--public-key` check signatures;
  `--out` sets the path; `--open` launches a browser.
- **`examples/hermes-dogfood/`** — reproducible evidence from a real Hermes agent
  guarded by Mizan (the `khwarizmi` plugin): the prompts, the signed hash-chained
  `receipts.jsonl`, verbatim `verify-output.txt`, and the generated `report.html`,
  with a README that verifies and reproduces it.

## [0.1.19] — 2026-06-02

### Changed
- **Precise tamper-evidence wording + tail-truncation anchoring.** A bare hash
  chain detects edits, insertions, reorders, and *middle* removals — but **tail
  truncation** leaves a valid prefix from genesis, so it needs an external
  anchor. `verify_log(...)` and `mizan verify-log` now take `--expect-head` /
  `--expect-count` to detect it; `verify-log` also prints the current head digest
  to anchor. README/docstring/AUDIT_STORAGE wording corrected accordingly.

## [0.1.18] — 2026-06-02

### Added — append-only audit trails (production gate #3)
- `mizan.chain.ReceiptLog`: an append-only, **hash-chained** JSONL receipt log.
  A signature proves each receipt is intact; the chain proves the *sequence*
  wasn't reordered, truncated, or inserted into (each link commits to the prior
  link's digest). Dependency-free.
- `mizan verify-log <file>`: verify chain integrity, and optionally every
  receipt's signature (`--secret-env` / `--public-key`). Exit: 0 ok · 1 chain
  broken · 2 a signature failed.
- `docs/AUDIT_STORAGE.md`: three-layer guidance (signature → hash chain →
  write-once storage + external head anchoring) and SIEM/OTel deployment.
- `examples/audit_log.py`; tests for tamper / removal / reorder detection.

## [0.1.17] — 2026-06-02

### Added — Ed25519 asymmetric signing (additive; HMAC stays the default)
- `mizan.signing` with `HmacSigner` (default, zero-dep) and `Ed25519Signer`
  (`pip install "mizan[ed25519]"`). Sign with `Receipt.to_v0(signer=…)` or
  `attest(…, signer=…)`; the signer holds the private key and an **auditor
  verifies with only the public key** — verification never hands out signing authority.
- `mizan keygen` generates an Ed25519 keypair (mode-600 file); `mizan verify
  --public-key key.json` verifies Ed25519 receipts and **auto-detects** the
  algorithm. New no-secret message for Ed25519.
- Schema + validators accept `algorithm: Ed25519` (128-hex signature).
- Fully gated: a bare `pip install mizan` keeps HMAC and needs no `cryptography`;
  Ed25519 paths friendly-error to the extra. `examples/ed25519_signing.py`.

## [0.1.16] — 2026-06-02

### Changed
- README stack table: corrected stale numbers (mizan.mcpscan now lists 7 rule
  families and references the reproducible benchmark — consistency 25/25,
  held-out 16/16, 0 hard FP; jabr 37 tests, muqabalah 23, toolproof 98/v0.5.2).
- verify-published gate hardened against propagation timing (polls for both
  wheel+sdist, retries provenance) — landed on main, first exercised by this release.

## [0.1.15] — 2026-06-02

### Changed
- **Benchmark reproduce command fixed**: the harness + corpus are repo-only, so
  `benchmark/run.py` now adds the checkout to `sys.path` and runs from a clone
  with no install or `PYTHONPATH` (a pip-installed `mizan` still wins). Command
  corrected in the docstring, generated doc, and README.
- **Path A (real `mcp-scan` comparison) — documented, not faked.** Verified the
  tool's current state: `mcp-scan` (Invariant) is now Snyk's `snyk-agent-scan`,
  which requires a Snyk account + `SNYK_TOKEN` + cloud (no offline mode) and
  scans configs/live MCP servers, not raw descriptors. A clean key-free
  head-to-head on this corpus isn't runnable here, so **no competitor numbers
  are claimed**; the benchmark doc records exactly how to run it with a token.

## [0.1.14] — 2026-06-02

### Changed — scanner hardening (measured before/after)
- `R-HOMO-001` now flags **fullwidth Latin letters/digits** (U+FF10–FF5A) — an
  ASCII-lookalike obfuscation used to spell directives past keyword scanners
  (e.g. `ｓｅｎｄ ａｌｌ ｆｉｌｅｓ`).
- New `R-EXFIL-003` (semantic, medium): **keyword-free bulk exfiltration** — an
  exfil verb + an all/every data scope + an external host (e.g. "transmit every
  document … to an outside host"). Medium severity, so it cannot add a *hard*
  false positive.
- Benchmark: **held-out 14/16 → 16/16**, consistency 25/25 unchanged, and **0
  new false positives** (still 0 hard / 5 soft). The two named held-out misses
  (`v2-7`, `v2-8`) are now caught.

## [0.1.13] — 2026-06-01

### Fixed
- **`mizan verify` claim-vs-execution enforcement was incomplete.** It gated the
  exit-5 path on the receipt's *self-declared* `verification` field, so a
  mismatching claim labelled `unverified`/`not_applicable` passed (exit 0). The
  recomputed `attest_claim(execution, claim)` is now **authoritative**: any claim
  that does not match execution exits `5` regardless of the declared field; a
  forged `verified` exits `1`; a genuine match exits `0` even if under-stated.

## [0.1.12] — 2026-06-01

### Added — claim-vs-execution ("signed action truth")
- `receipt_v0.attest_claim(execution, claim)` and `receipt_v0.attest(receipt,
  claimed_tool=…, claimed_result=…, secret=…)`: weigh what an agent *claims* it
  did against what Mizan *observed*. Pure hash comparison, dependency-free.
- `to_v0` now auto-computes `verification` from `execution`+`claim` when there's
  no toolproof verify stage.
- **`mizan verify` enforces it**: exit `5` when the agent's claim doesn't match
  execution (`--allow-claim-mismatch` to override), and exit `1` if a signed
  receipt forges `verification: verified` while the hashes disagree (a signer
  cannot lie about the verdict).
- `examples/attest_claim.py` (bare install) + tests.

## [0.1.11] — 2026-06-01

### Added
- **`examples/full_pipeline_demo.py`** — the whole scale in one run: a poisoned
  MCP tool (BiDi finding), an Arabic request with a contradiction (caught), a
  transliterated argument (blocked by mtg), and a lying agent (rejected by
  toolproof) — all weighed into one signed Receipt v0 that `mizan verify` passes,
  plus a tamper that fails. One file, one command (`pip install "mizan[all]"`).
- Smoke test that runs the demo and verifies its receipt (skips without the
  primitives installed).

## [0.1.10] — 2026-06-01

### Added
- **Reproducible MCP-poisoning benchmark** (`benchmark/`): committed corpus in
  three separated splits (consistency / held-out adversarial / clean
  false-positive) and a harness (`python benchmark/run.py`) that reports **per
  category** catch / miss / false-positive — no single aggregate score, with a
  generic-coverage column and the held-out misses listed honestly. Measured:
  consistency 25/25, held-out 14/16 (2 real misses surfaced), **0 hard false
  positives**. Mizan-only numbers; a real `mcp-scan` head-to-head is a
  documented follow-up. Regenerates `docs/MCP_POISONING_BENCHMARK.md`.
- A regression-guard test (consistency fully caught + no hard FP).

### Changed
- README: replace the stale "~63% recall" claim with the reproducible benchmark.

## [0.1.9] — 2026-06-01

### Changed (CI/release hardening — no library change)
- Release workflow: `skip-existing: true` so a transient mid-upload network drop
  can be recovered by re-running the failed job, plus a **`verify-published`**
  gate job that fails the release if the version, wheel, sdist, provenance
  (HTTP 200 each), or an install smoke is missing. A partial release can no
  longer pass silently.
- `docs/SUPPLY_CHAIN.md`: release-resilience + manual recovery steps.

## [0.1.8] — 2026-06-01

### Changed (docs precision — no code change)
- Clarify the OpenAI adapter's scope: it records and signs the *observed* tool
  execution (`verification: not_applicable`). `mizan verify` proves the receipt
  is signed and untampered — **not** that an agent's later *claim* matches what
  ran. Claim-vs-execution is a separate layer (the `verify` stage / `toolproof`).
- Refresh stale roadmap text (primitives are on PyPI; the Receipt spec is frozen
  at v0; CI is live) and list claim-vs-execution attestation as the next layer.

## [0.1.7] — 2026-06-01

### Added (additive)
- **OpenAI Agents SDK adapter** (`mizan.adapters.openai.receipt_tool`): wrap a
  tool so every call emits a signed Receipt v0 — captures tool name, args hash,
  result hash, observed status (`ok`/`error`), and agent/model/run ids.
  Import-safe (no `openai`/`agents` import); compose under `@function_tool`.
  Sync + async tools; leading `RunContextWrapper` excluded from the args hash;
  `run_id` falls back to the active OTel trace id. `pip install "mizan[openai]"`
  adds the SDK for end-to-end use.
- `examples/openai_agents_receipt.py`.

## [0.1.6] — 2026-06-01

### Added (all additive — `Receipt.to_dict()` unchanged)
- **Receipt v0**: `Receipt.to_v0(secret=…)` emits the signed evidence document
  defined in `docs/RECEIPT_SPEC.md` — hashed input/output, `decision`,
  `execution`, `claim`, `verification`, ids/timestamp, and a signature envelope.
- **`mizan verify` and `mizan diff` CLIs** (console script + `python -m mizan`),
  dependency-free: structural validation + RFC 8785-aligned HMAC signature
  check; full JSON-Schema validation when `jsonschema` is installed.
- JSON Schema shipped as package data (`mizan/schemas/receipt-v0.schema.json`).
- `examples/receipts/{passed,blocked,tampered}.json` are now code-generated
  fixtures with a drift-guard test.

## [0.1.5] — 2026-06-01

### Changed
- **Removed the `~/Projects` `sys.path` fallback** from `mizan.preflight`. A
  published wheel must not import primitives from local dev checkouts; they now
  come only from a real install (`pip install mizan[preflight]`).
- Refreshed stale docstrings/comments that said the primitives were "not yet on
  PyPI" — they are published.

### Added
- `docs/SUPPLY_CHAIN.md`: Trusted Publishing, OIDC, provenance verification, and
  a maintainer release checklist.
- This `CHANGELOG.md`.
- CI: a job that installs the **published** `mizan[all]` from PyPI and runs the
  pipeline end to end (in addition to source-tree tests and the scanner-only job).

## [0.1.4] — 2026-05-31

### Added
- The reliability pipeline is now plain-pip installable: all five primitives are
  on PyPI. Extras restored with real deps and conservative caps:
  `mizan[preflight]` (jabr/muqabalah/qadiya), `mizan[verify]`
  (toolproof-receipt), `mizan[all]` (+ mtg-guards + otel).

### Changed
- `MissingPrimitiveError` now points to `pip install mizan[preflight]`.
- CI installs the published packages via the `[all]` extra.

## [0.1.3] — 2026-05-31

### Fixed
- Scanner is genuinely standalone: lazy-load the preflight layer so
  `import mizan` and `mizan.mcpscan` work with zero primitives installed.
- `__version__` is derived from package metadata (was a stale hardcoded string).

### Added
- Friendly `MissingPrimitiveError` instead of a bare `ModuleNotFoundError`.
- CI job asserting the scanner works without primitives.

## [0.1.2] — 2026-05-31

### Added
- Trove classifiers, CI test matrix (Python 3.10–3.13), README badges.
- PyPI Trusted Publishing (OIDC) release workflow; `SECURITY.md`; Dependabot.
- GitHub Actions pinned to commit SHAs.

## [0.1.1] — 2026-05-31

### Changed
- Self-contained README quickstart; added project URLs.
- Removed git-based extras that PyPI rejects.

## [0.1.0] — 2026-05-31

- First public release on PyPI: `mizan.mcpscan` scanner, `preflight`,
  `ToolGate`, receipts, and OTel export.

[0.1.5]: https://github.com/Moshe-ship/mizan/releases/tag/v0.1.5
[0.1.4]: https://github.com/Moshe-ship/mizan/releases/tag/v0.1.4
[0.1.3]: https://github.com/Moshe-ship/mizan/releases/tag/v0.1.3
[0.1.2]: https://github.com/Moshe-ship/mizan/releases/tag/v0.1.2
[0.1.1]: https://github.com/Moshe-ship/mizan/releases/tag/v0.1.1
[0.1.0]: https://github.com/Moshe-ship/mizan/releases/tag/v0.1.0
