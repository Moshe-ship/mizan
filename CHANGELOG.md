# Changelog

All notable changes to `mizan` are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project adheres to
semantic versioning (pre-1.0: minor = features, patch = fixes/hardening).

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
