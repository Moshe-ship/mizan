# Security Policy

Mizan is a reliability and security tool (it scans MCP tool descriptors for
poisoning, restores prompts, and constrains tool arguments), so its own
integrity matters. This document explains how to report a vulnerability and
what guarantees the project makes.

## Supported versions

Mizan is pre-1.0. Only the latest released version on PyPI receives security
fixes. Pin a version you have reviewed if you need stability.

| Version | Supported |
| ------- | --------- |
| latest `0.1.x` | ✅ |
| older | ❌ |

## Reporting a vulnerability

**Do not open a public issue for security reports.**

Use GitHub's private vulnerability reporting:
<https://github.com/Moshe-ship/mizan/security/advisories/new>

If you cannot use that, email the maintainer with `[mizan-security]` in the
subject. Please include:

- affected version (`pip show mizan`)
- a minimal reproduction (tool descriptor / input that triggers the issue)
- the impact you observed (e.g. a poisoned tool the scanner failed to flag)

You can expect an acknowledgement of your report and, once a fix ships, credit
in the release notes unless you prefer to remain anonymous.

## Scope

In scope:

- scanner false negatives (a real poisoning technique `mizan.mcpscan` misses)
- `preflight` / `ToolGate` bypasses (input that should be escalated but is allowed)
- receipt forgery (a signed receipt that verifies against tampered content)

Out of scope:

- vulnerabilities in the not-yet-published primitive packages
  (`jabr`/`muqabalah`/`qadiya`/`mtg`/`toolproof`) — report those on their repos
- issues requiring a malicious local environment the user already controls

## Supply chain

Release and CI workflows pin all GitHub Actions to commit SHAs, and publishing
uses PyPI Trusted Publishing (OIDC) — no long-lived API tokens are stored.
