# A multilingual MCP tool-poisoning benchmark

Most MCP security scanners inspect tool metadata for English suspicious-pattern
signals. But the tool surface is text, and text hides attacks in ways English
pattern-matching does not see: right-to-left overrides, invisible and TAG-block
characters, homoglyphs, Arabizi (Latin-script Arabic), and Arabic/English
code-switched directives. This is a small, honest benchmark for that gap — and
for the scanner (`mizan.mcpscan`) built to close it.

> **Framing.** This does not claim to beat any scanner. Generic scanners focus
> on generic/static metadata risks; Mizan adds a multilingual Unicode/dialect
> layer and carries findings into runtime receipts. The numbers below are
> measured, including where the scanner fails.

## What it measures

Each case is an MCP tool descriptor (name, description, and optionally input
schema with parameter descriptions). A scanner must flag poisoned descriptors
and leave legitimate ones alone — **including legitimate tools that look
dangerous** (security tools that mention "exfiltration", benign `token`/`secret`
names, and legitimate Arabic instructions like "اقرأ الوثائق / read the docs").

Rule families: BiDi controls, invisible/TAG payloads, homoglyph/mixed-script,
Arabizi, Arabic/English code-switch directives, semantic exfiltration (EN+AR),
and instruction override.

## Methodology — three tiers, deliberately separated

The point of separating them is honesty: a single self-authored number is
self-congratulatory.

1. **Consistency corpus** — cases written from the same rule logic. Measures
   internal consistency and false-positive discipline, not generalization.
2. **Held-out v1** — cases authored to attack the rules' assumptions. Exposed
   gaps; the rules were then fixed *by failure category*, never tuned to the
   exact cases.
3. **Fresh held-out v2** — new cases authored *after* the fixes, never trained
   against. This is the generalization number.

## Results

| tier | recall | hard false-positives | notes |
|---|---|---|---|
| consistency | 25/25 | 0/23 | incl. tricky benign negatives (`count_tokens`, `secret_santa`, `hash_password`) |
| held-out v1 (post-fix, now seen) | 8/8 | 0/10 | regression check, not generalization |
| **fresh held-out v2** | **6/8** | **0/7** | the honest generalization number |

**Across all three tiers: 0 hard false positives.** Recall on genuinely novel
attacks is ~63%. Structural Unicode rules (BiDi, homoglyph, invisible) and
**parameter-surface scanning** generalize well; semantic and obfuscation
coverage is partial.

### Where it fails (recorded, not hidden)
- Whitespace/spaced-out and cross-field payloads are caught only after a
  normalization + holistic pass, at medium confidence.
- Fullwidth-character leetspeak and pure-synonym exfiltration ("transmit … to an
  outside host") are missed — deliberately not chased with more regexes.
- ZWNJ between Latin letters is flagged; ZWNJ inside Arabic/Persian is **not**
  (it is legitimate there) — preserving multilingual credibility over recall.

## Product stance

**Audit/warn-ready, not default-block.** One blocking false positive per ten
clean tools would be too many to auto-block; the scanner is built to run in
audit or warn mode, escalating to block only on high-confidence structural
findings. Semantic findings are advisory (medium).

## Reproduce

```bash
pip install mizan
cd experiments/mcp-poisoning-probe
python corpus.py        && python evaluate.py
python held_out.py      && python held_out_eval.py
python held_out_v2.py   && python held_out_eval.py held_out_v2.jsonl
```

Corpus, evaluators, and raw findings: [`experiments/mcp-poisoning-probe/`](../experiments/mcp-poisoning-probe).
Scanner: [`mizan/mcpscan.py`](../mizan/mcpscan.py). Complementary to the
arXiv:2603.22489 MCP threat-modeling line and the OWASP Agentic Top 10 (2026).
