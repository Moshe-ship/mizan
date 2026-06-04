"""``mizan scan`` — scan MCP tool descriptors for poisoning, with an Arabic mode.

    mizan scan tools.json
    mizan scan --arabic tools.json
    mizan scan --arabic tools.json --receipt-log receipts.jsonl

Plain scan runs the multilingual detectors (BiDi, invisible, homoglyph, Arabizi,
code-switch, semantic exfil, override) and reports findings flat.

``--arabic`` separates **Arabic-specific** risk (Arabizi, Arabic/English
code-switching, transliteration, Arabic semantic exfil) from **generic**
Unicode/tool-poisoning risk (BiDi, invisible, homoglyph, override), reports an
`arabic_risk` and `generic_risk` level, and adds a **transliteration** check
(romanized Arabic directives in pure Latin script) that the plain scan does not
run — so the two modes produce different, assertable output.

With ``--receipt-log`` each scanned tool also gets a signed Receipt v0 appended
to a hash-chained log (verifiable with ``mizan verify-log`` / ``mizan report``).
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Optional

from mizan.mcpscan import Finding, _fields, _snip, decide, scan_tool, ScanConfig

# Arabic / Arabic-Supplement script range.
_ARABIC_SCRIPT = re.compile(r"[؀-ۿݐ-ݿ]")

# Families that are intrinsically Arabic-specific. (Semantic findings are
# classified by whether their evidence actually contains Arabic script.)
_ARABIC_FAMILIES = {"arabizi", "codeswitch", "transliteration"}

# Transliteration: romanized Arabic *directives* written in pure Latin script —
# an instruction English keyword scanners and the mixed-script code-switch rule
# both miss (no Arabic characters present, no English exfil keywords). Narrow on
# purpose: a romanized directive verb must co-occur with a data scope/object or
# an external destination, to keep false positives low.
_TRANSLIT_VERB = (
    r"\b(?:irsal|arsil|ib'?ath|ibaath|ihzif|ihdhif|imsah|saddir|sadder|"
    r"naffidh|naffith|shagh?ghil|shaghil|tajaa?hal|hammil|irfaa)\b"
)
_TRANSLIT_OBJ = r"\b(?:kul|jami[ae]|malaf(?:at)?|miftah|sirr[iy]?|bayanat|kalimat)\b"
_TRANSLIT_OBJECT = re.compile(_TRANSLIT_VERB + r"[^\n]{0,40}" + _TRANSLIT_OBJ, re.IGNORECASE)
_TRANSLIT_EXFIL = re.compile(
    _TRANSLIT_VERB + r"[^\n]{0,40}(?:https?://|\.ssh|id_rsa|"
    r"[A-Za-z0-9.-]+\.(?:com|net|io|org|ru|xyz))",
    re.IGNORECASE,
)


def transliteration_findings(tool: dict) -> list[Finding]:
    """Arabic-mode-only check: romanized Arabic directive in tool metadata."""
    for field, text in _fields(tool):
        if _TRANSLIT_OBJECT.search(text) or _TRANSLIT_EXFIL.search(text):
            return [Finding(
                "R-TRANSLIT-001", "transliteration", "medium",
                "Romanized Arabic directive (transliteration) — an instruction in "
                "Latin-script Arabic that English keyword and mixed-script checks miss.",
                evidence=_snip(text),
                remediation="Treat romanized Arabic as untrusted instruction text; "
                            "transliterate to Arabic and re-scan for directives.",
                field=field,
            )]
    return []


def is_arabic_specific(f: Finding) -> bool:
    return f.family in _ARABIC_FAMILIES or bool(_ARABIC_SCRIPT.search(f.evidence or ""))


def _max_sev(findings: list[Finding]) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return max((f.severity for f in findings), key=lambda s: order.get(s, -1), default="none")


def scan_one(tool: dict, *, arabic: bool) -> list[Finding]:
    """All findings for a tool; in Arabic mode, also the transliteration check."""
    findings = list(scan_tool(tool).findings)
    if arabic:
        have = {(f.rule_id, f.field) for f in findings}
        for tf in transliteration_findings(tool):
            if (tf.rule_id, tf.field) not in have:
                findings.append(tf)
    return findings


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _fmt(f: Finding) -> list[str]:
    return [
        f"    [{f.severity:6}] {f.rule_id:16} {f.family}"
        + (f"  ({f.field})" if f.field else ""),
        f"       {f.message}",
        f"       evidence: {f.evidence[:80]}",
    ]


def render_plain(name: str, findings: list[Finding]) -> str:
    if not findings:
        return f"✓ {name}: no findings"
    out = [f"⚠ {name}: {len(findings)} finding(s) [{_max_sev(findings)}]"]
    for f in findings:
        out += _fmt(f)
    return "\n".join(out)


def render_arabic(name: str, findings: list[Finding]) -> str:
    arabic = [f for f in findings if is_arabic_specific(f)]
    generic = [f for f in findings if not is_arabic_specific(f)]
    if not findings:
        return f"✓ {name}: no findings  ·  arabic_risk: none  ·  generic_risk: none"
    out = [f"⚠ {name}  ·  arabic_risk: {_max_sev(arabic)}  ·  generic_risk: {_max_sev(generic)}"]
    out.append("  Arabic-specific (arabizi · code-switch · transliteration · Arabic exfil):")
    out += (["    — none"] if not arabic else [l for f in arabic for l in _fmt(f)])
    out.append("  Generic (bidi · invisible · homoglyph · override):")
    out += (["    — none"] if not generic else [l for f in generic for l in _fmt(f)])
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# Receipts
# --------------------------------------------------------------------------- #
def _emit_receipt(log, name: str, findings: list[Finding], action: str,
                  *, secret, signer) -> None:
    from mizan.receipt import Receipt, StageRecord
    arabic = [f.to_dict() for f in findings if is_arabic_specific(f)]
    generic = [f.to_dict() for f in findings if not is_arabic_specific(f)]
    rec = Receipt(f"tool:{name}", action, stages=(StageRecord(
        stage="scan", tool="mcpscan", ok=(not findings), changes=len(findings),
        detail={"tool": name, "arabic_risk": _max_sev([f for f in findings if is_arabic_specific(f)]),
                "generic_risk": _max_sev([f for f in findings if not is_arabic_specific(f)]),
                "arabic_findings": arabic, "generic_findings": generic}),))
    doc = rec.to_v0(secret=secret, signer=signer, agent_id="mizan-scan", tool=name)
    log.append(doc)


def _load_tools(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict) and isinstance(data.get("tools"), list):
        return data["tools"]
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    raise ValueError("expected a tool object, a list, or {\"tools\": [...]}")


def cmd_scan(args: Any) -> int:
    try:
        tools = _load_tools(args.path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"✗ cannot read tools from {args.path}: {exc}", file=sys.stderr)
        return 1

    arabic = bool(getattr(args, "arabic", False))
    mode = getattr(args, "mode", "audit")

    log = secret = signer = None
    rlog = getattr(args, "receipt_log", None)
    if rlog:
        from mizan.chain import ReceiptLog
        log = ReceiptLog(rlog)
        secret = os.environ.get(getattr(args, "secret_env", "") or "") or None

    worst = "allow"
    rank = {"allow": 0, "warn": 1, "block": 2}
    for tool in tools:
        findings = scan_one(tool, arabic=arabic)
        name = str(tool.get("name", "?"))
        print(render_arabic(name, findings) if arabic else render_plain(name, findings))
        # decision (same findings drive it in both modes)
        from mizan.mcpscan import ScanResult
        d = decide(ScanResult(name, tuple(findings)), ScanConfig(mode=mode))
        if rank[d.action] > rank[worst]:
            worst = d.action
        if log is not None:
            _emit_receipt(log, name, findings, d.action, secret=secret, signer=signer)

    if log is not None:
        print(f"\n→ signed receipts appended to {rlog}", file=sys.stderr)
    return {"allow": 0, "warn": 1, "block": 2}[worst]
