# Multilingual MCP tool-poisoning benchmark — measured

> **Mizan-only measurements.** These numbers come from running `mizan.mcpscan`
> over a committed corpus. **No competitor (e.g. `mcp-scan`) numbers are claimed**
> here — a real head-to-head is a documented follow-up (see *Follow-up*). The point
> of three separated splits is honesty: a single self-authored aggregate score is not.

Reproduce from a clone (no install needed): `git clone https://github.com/Moshe-ship/mizan && cd mizan && python benchmark/run.py`. Corpus: [`benchmark/corpus/`](../benchmark/corpus/).

## 1. Consistency / regression (known patterns)

Poison descriptors with patterns the rules encode. Caught **25/25**.

| family | total | caught | missed | generic scanners |
|---|---|---|---|---|
| `arabizi` | 3 | 3 | 0 | Rarely — Latin-script Arabic is a multilingual gap (Mizan depth) |
| `bidi` | 3 | 3 | 0 | Commonly covered (OWASP Prompt-Injection cheat sheet flags BiDi/RTL overrides) |
| `codeswitch` | 3 | 3 | 0 | Rarely — Arabic/English embedded directives (Mizan depth) |
| `homoglyph` | 4 | 4 | 0 | Commonly covered (confusables/mixed-script detection is widespread) |
| `invisible` | 3 | 3 | 0 | Partially (zero-width often caught; ZWNJ-between-letters is subtler) |
| `override` | 2 | 2 | 0 | Partially (imperative directives common; spacing/tab evasion subtler) |
| `semantic` | 7 | 7 | 0 | Partially (English exfil keywords common; AR / synonyms / base64 subtler) |

## 2. Held-out adversarial (fresh variants)

Variants **not** directly encoded — the honest generalization test. Caught **16/16**; misses are listed per family.

| family | total | caught | missed | generic scanners |
|---|---|---|---|---|
| `arabizi` | 2 | 2 | 0 | Rarely — Latin-script Arabic is a multilingual gap (Mizan depth) |
| `bidi` | 2 | 2 | 0 | Commonly covered (OWASP Prompt-Injection cheat sheet flags BiDi/RTL overrides) |
| `codeswitch` | 1 | 1 | 0 | Rarely — Arabic/English embedded directives (Mizan depth) |
| `cross-field` | 1 | 1 | 0 | Partially (multi-field dataflow is uneven across tools) |
| `homoglyph` | 3 | 3 | 0 | Commonly covered (confusables/mixed-script detection is widespread) |
| `invisible` | 1 | 1 | 0 | Partially (zero-width often caught; ZWNJ-between-letters is subtler) |
| `override` | 2 | 2 | 0 | Partially (imperative directives common; spacing/tab evasion subtler) |
| `semantic` | 4 | 4 | 0 | Partially (English exfil keywords common; AR / synonyms / base64 subtler) |

## 3. Clean false-positive set (legit confusables)

Legitimate tools that look dangerous: security scanners, benign `token`/`secret`/`ssh` mentions, legit Arabic, and mixed-language text. **40** items.

- **Hard false positives (high-severity on a clean tool): 0** ✓
- Soft flags (medium-severity, audit/warn not block): 5 — neg-16:clean, ho-11:ssh-mgr-negated, ho-15:ar-read-docs, ho-17:pw-reset, v2-12:secret-param

## Where the edge actually is

Generic English/Unicode scanners and the OWASP cheat sheet already cover **bidi**,
**homoglyph**, and much of **invisible** — Mizan does **not** claim to have invented
Unicode detection. Mizan's measured differentiation is the multilingual/Arabic layer:
**arabizi** (Latin-script Arabic), **codeswitch** (Arabic/English embedded directives),
and the Arabic side of **semantic** exfiltration — categories the held-out split shows
are where Arabic morphology/dialect/transliteration depth matters.

## Follow-up — real `mcp-scan` comparison (not yet run)

A live head-to-head against Invariant's `mcp-scan` is **not** included. When run it will:
pin the `mcp-scan` version, document the install command and the descriptor/input
conversion, run the **same** corpus, and publish the exact command + output — updating
this doc only with measured numbers, per category.
