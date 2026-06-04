# Supply Chain & Provenance

Mizan is a reliability/security tool, so its own distribution is meant to be
verifiable. This document explains how the Mizan stack is published and how you
can independently verify what you install.

## How it's published

Every package in the stack — `mizan` and the five primitives (`jabr`,
`muqabalah`, `qadiya`, `mtg-guards`, `toolproof-receipt`) — is published to
PyPI via **Trusted Publishing (OpenID Connect)**:

- **No API tokens or passwords** are stored anywhere. Publishing authority is
  delegated to a specific GitHub Actions workflow via short-lived OIDC tokens.
- Each release is built and uploaded by a tag-triggered `release.yml` workflow.
- All GitHub Actions in the release workflow are **pinned to commit SHAs**, not
  mutable tags.
- Each uploaded wheel and sdist carries **PEP 740 digital attestations**
  (provenance), signed during the workflow and recorded in a transparency log.

## Verify a package's provenance

PyPI exposes attestations through its Integrity API. For any file:

```bash
# 1. find the wheel/sdist filename
curl -s https://pypi.org/pypi/mizan/json | python3 -c \
  "import sys,json; print([u['filename'] for u in json.load(sys.stdin)['urls']])"

# 2. fetch its provenance (HTTP 200 = attestation exists)
curl -s "https://pypi.org/integrity/mizan/0.1.5/mizan-0.1.5-py3-none-any.whl/provenance" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); b=d['attestation_bundles'][0]; \
    print('publisher:', b['publisher']['kind'], b['publisher'].get('repository'), b['publisher'].get('workflow'))"
```

Expected publisher: `GitHub Moshe-ship/mizan release.yml`. The primitives report
their own `Moshe-ship/<repo>` + `release.yml`.

You can also verify with the official tooling:

```bash
pip install pypi-attestations
python -m pypi_attestations verify pypi --repository \
  https://github.com/Moshe-ship/mizan mizan-0.1.5-py3-none-any.whl
```

## Install names vs import names

Two packages differ between PyPI name and import name:

| PyPI package | `import` |
| --- | --- |
| `mtg-guards` | `mtg` |
| `toolproof-receipt` | `toolproof` |

## Release checklist (maintainers)

Before tagging `vX.Y.Z`:

- [ ] `twine check dist/*` passes for wheel and sdist
- [ ] fresh-venv install test: `pip install <wheel>` then import the package
- [ ] for `mizan`: `pip install "mizan[all]"` in a clean venv runs `preflight` end to end
- [ ] CI is green on `main` (matrix + scanner-standalone + PyPI smoke)

After publishing (the `verify-published` CI job enforces these automatically):

- [ ] provenance returns HTTP 200 for **both** the wheel and the sdist (Integrity API)
- [ ] PyPI page resolves the new version; `pip install` picks it up
- [ ] GitHub Release created with the install command and provenance note

## Release pipeline resilience

The release workflow has two safety properties:

- **`skip-existing: true`** on the publish step — a transient mid-upload network
  drop (`Response ended prematurely`) can be recovered by re-running the failed
  job; already-uploaded files are skipped instead of causing a 400.
- **A `verify-published` gate job** runs after publish and fails the release
  loudly if the tagged version is missing from PyPI, is missing the wheel or
  sdist, lacks provenance (HTTP 200) for either file, or fails an install smoke.
  So a *partial* release cannot pass silently even with `skip-existing`.

**If a publish fails (transient upload error):**

1. Confirm nothing partial landed: `curl -s https://pypi.org/pypi/mizan/<version>/json`
   → a `404` means the version is clean to retry.
2. Re-run just the failed job: `gh run rerun <run-id> --failed`.
3. The `verify-published` gate confirms files + provenance before the run is green.

A PyPI version is immutable — never re-tag; if a *bad* artifact landed, bump the
patch version rather than trying to overwrite.

## Honest scope

This covers **distribution integrity** (token-free, attested, reproducible
workflows). It is *not* a claim of total security. Repository-level hardening is
in place: branch protection with required CI on PRs, no force-push or branch
deletion, and immutable version tags. `enforce_admins` is off by design for a
solo maintainer, so required human review on every change is the remaining
pre-1.0 gap.
