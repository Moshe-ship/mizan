"""Reproducible multilingual MCP tool-poisoning benchmark for `mizan.mcpscan`.

Three deliberately separated splits (corpus under benchmark/corpus/):
  1. consistency  — known patterns the scanner should catch (regression)
  2. heldout      — fresh adversarial variants not encoded in the rules
  3. clean        — legitimate confusables that must NOT be flagged

Reports per-family catch / miss / false-positive and writes the measured
numbers into docs/MCP_POISONING_BENCHMARK.md. No single aggregate "score" is
the headline — per-category honesty is the point. These are Mizan-only
measurements; no competitor numbers are produced here (see the doc's follow-up).

The harness and corpus live in the repo (not the wheel), so reproduce from a clone:

    git clone https://github.com/Moshe-ship/mizan && cd mizan
    python benchmark/run.py            # prints report + rewrites the doc
    python benchmark/run.py --check    # prints report, exits 1 on regression

No install is required (the script adds the checkout to sys.path); a pip-installed
`mizan` takes precedence if present.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import defaultdict

# Run straight from a clone with no install: make the repo's `mizan` importable.
# (A pip-installed `mizan` still works; this only adds the checkout as a fallback.)
_REPO = pathlib.Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.append(str(_REPO))

from mizan.mcpscan import scan_tool  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
DOC = ROOT.parent / "docs" / "MCP_POISONING_BENCHMARK.md"

# Honest note on what a generic English/Unicode scanner is likely to cover,
# per detector family (grounded in OWASP cheat-sheet + general confusables tools).
GENERIC_COVERAGE = {
    "bidi": "Commonly covered (OWASP Prompt-Injection cheat sheet flags BiDi/RTL overrides)",
    "invisible": "Partially (zero-width often caught; ZWNJ-between-letters is subtler)",
    "homoglyph": "Commonly covered (confusables/mixed-script detection is widespread)",
    "arabizi": "Rarely — Latin-script Arabic is a multilingual gap (Mizan depth)",
    "codeswitch": "Rarely — Arabic/English embedded directives (Mizan depth)",
    "semantic": "Partially (English exfil keywords common; AR / synonyms / base64 subtler)",
    "override": "Partially (imperative directives common; spacing/tab evasion subtler)",
    "cross-field": "Partially (multi-field dataflow is uneven across tools)",
}


def _load(name: str) -> list[dict]:
    return [json.loads(l) for l in (CORPUS / f"{name}.jsonl").read_text().splitlines() if l.strip()]


def _scan(tool: dict):
    res = scan_tool(tool)
    findings = list(res.findings)
    sev = {f.severity for f in findings}
    return findings, sev


def _poison_split(name: str):
    """Per-family caught/missed for a poison split. Caught = a medium+ finding."""
    per = defaultdict(lambda: {"total": 0, "caught": 0, "missed_ids": []})
    for item in _load(name):
        fam = item["family"]
        _, sev = _scan(item["tool"])
        per[fam]["total"] += 1
        if sev & {"medium", "high"}:
            per[fam]["caught"] += 1
        else:
            per[fam]["missed_ids"].append(item["id"])
    return per


def _clean_split():
    """False positives on legit confusables. Hard FP = a HIGH-severity finding."""
    hard, soft = [], []
    total = 0
    for item in _load("clean"):
        total += 1
        _, sev = _scan(item["tool"])
        if "high" in sev:
            hard.append((item["id"], item["technique"]))
        elif "medium" in sev:
            soft.append((item["id"], item["technique"]))
    return total, hard, soft


def _fam_table(per: dict) -> list[str]:
    rows = ["| family | total | caught | missed | generic scanners |", "|---|---|---|---|---|"]
    for fam in sorted(per):
        d = per[fam]
        miss = f"{d['total'] - d['caught']}" + (f" ({', '.join(d['missed_ids'])})" if d["missed_ids"] else "")
        rows.append(f"| `{fam}` | {d['total']} | {d['caught']} | {miss} | {GENERIC_COVERAGE.get(fam, '—')} |")
    return rows


def build_report() -> tuple[str, bool]:
    consistency = _poison_split("consistency")
    heldout = _poison_split("heldout")
    clean_total, hard_fp, soft_fp = _clean_split()

    c_total = sum(d["total"] for d in consistency.values())
    c_caught = sum(d["caught"] for d in consistency.values())
    h_total = sum(d["total"] for d in heldout.values())
    h_caught = sum(d["caught"] for d in heldout.values())

    regression_ok = c_caught == c_total and not hard_fp

    L = []
    L.append("# Multilingual MCP tool-poisoning benchmark — measured\n")
    L.append("> **Mizan-only measurements.** These numbers come from running `mizan.mcpscan`")
    L.append("> over a committed corpus. **No competitor (e.g. `mcp-scan`) numbers are claimed**")
    L.append("> here — a real head-to-head is a documented follow-up (see *Follow-up*). The point")
    L.append("> of three separated splits is honesty: a single self-authored aggregate score is not.\n")
    L.append("Reproduce from a clone (no install needed): "
             "`git clone https://github.com/Moshe-ship/mizan && cd mizan && python benchmark/run.py`. "
             "Corpus: [`benchmark/corpus/`](../benchmark/corpus/).\n")

    L.append("## 1. Consistency / regression (known patterns)\n")
    L.append(f"Poison descriptors with patterns the rules encode. Caught **{c_caught}/{c_total}**.\n")
    L += _fam_table(consistency)

    L.append("\n## 2. Held-out adversarial (fresh variants)\n")
    L.append(f"Variants **not** directly encoded — the honest generalization test. "
             f"Caught **{h_caught}/{h_total}**; misses are listed per family.\n")
    L += _fam_table(heldout)

    L.append("\n## 3. Clean false-positive set (legit confusables)\n")
    L.append(f"Legitimate tools that look dangerous: security scanners, benign `token`/`secret`/`ssh` "
             f"mentions, legit Arabic, and mixed-language text. **{clean_total}** items.\n")
    L.append(f"- **Hard false positives (high-severity on a clean tool): {len(hard_fp)}**"
             + (f" — {', '.join(i for i, _ in hard_fp)}" if hard_fp else " ✓"))
    L.append(f"- Soft flags (medium-severity, audit/warn not block): {len(soft_fp)}"
             + (f" — {', '.join(f'{i}:{t}' for i, t in soft_fp)}" if soft_fp else ""))

    L.append("\n## Where the edge actually is\n")
    L.append("Generic English/Unicode scanners and the OWASP cheat sheet already cover **bidi**,")
    L.append("**homoglyph**, and much of **invisible** — Mizan does **not** claim to have invented")
    L.append("Unicode detection. Mizan's measured differentiation is the multilingual/Arabic layer:")
    L.append("**arabizi** (Latin-script Arabic), **codeswitch** (Arabic/English embedded directives),")
    L.append("and the Arabic side of **semantic** exfiltration — categories the held-out split shows")
    L.append("are where Arabic morphology/dialect/transliteration depth matters.\n")

    L.append("## Follow-up — real `mcp-scan` comparison (not yet run)\n")
    L.append("A live head-to-head against Invariant's `mcp-scan` is **not** included. When run it will:")
    L.append("pin the `mcp-scan` version, document the install command and the descriptor/input")
    L.append("conversion, run the **same** corpus, and publish the exact command + output — updating")
    L.append("this doc only with measured numbers, per category.")

    return "\n".join(L) + "\n", regression_ok


def main() -> int:
    report, ok = build_report()
    check = "--check" in sys.argv
    if not check:
        DOC.write_text(report)
        print(f"wrote {DOC}")
    print(report)
    if check and not ok:
        print("REGRESSION: a consistency-set miss or a hard false positive.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
