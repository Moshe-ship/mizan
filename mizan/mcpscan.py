"""mizan.mcpscan — multilingual / Unicode MCP tool-surface scanner.

Inspects an MCP tool descriptor (name, description, input schema) for poisoning
vectors that English-pattern / rendered-text inspection misses: BiDi controls,
invisible & TAG-block payloads, homoglyph/confusable scripts, Arabizi and
Arabic/English code-switched directives, plus semantic exfiltration phrasing in
English and Arabic.

Each rule has a stable ID, severity, an evidence snippet, and a remediation.
A scan folds into the shared :class:`~mizan.receipt.Receipt` (STAGE_SCAN), so a
tool-surface finding carries through to runtime receipts.

This is *complementary* to generic scanners (mcp-scan / Cisco): it adds the
multilingual/Unicode layer and the runtime-receipt carry-through. It does not
replace their cloud LLM classifiers for general English semantic attacks.

Built on the verified primitives in `mtg` (bidi, uts39, translit,
prompt_injection). No new detection research — assembly + a semantic rule.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from mizan.receipt import StageRecord, STAGE_SCAN

sys.path.insert(0, str(Path.home() / "Projects" / "mtg"))

from mtg.bidi import detect_bidi_threats  # noqa: E402
from mtg.uts39 import analyze as uts39_analyze  # noqa: E402
from mtg.translit import looks_like_arabizi, detect_script  # noqa: E402
from mtg.prompt_injection import detect_prompt_injection  # noqa: E402

SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2}


@dataclass(frozen=True)
class Finding:
    rule_id: str
    family: str
    severity: str            # low | medium | high
    message: str
    evidence: str            # short snippet / codepoints that triggered the rule
    remediation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "family": self.family,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence[:120],
            "remediation": self.remediation,
        }


# Semantic exfiltration / privilege phrasing — English + Arabic. This is the
# rule the plain-English control exposed: override-pattern detection alone is
# not enough.
_EXFIL_EN = re.compile(
    r"(?:read|cat|exfiltrate|leak|upload|send|post|curl|wget)[^\n]{0,60}"
    r"(?:\.ssh|id_rsa|private[ _]?key|secret|token|password|credential|all files|/etc/|\benv\b)"
    r"|bypass[^\n]{0,30}(?:approval|confirmation|review|guard)"
    r"|use this tool for (?:all|every)"
    r"|ignore (?:all )?(?:previous|prior) (?:instructions|context)",
    re.IGNORECASE,
)
_EXFIL_AR = [
    "أرسل جميع الملفات", "أرسل الملفات", "اقرأ المفتاح", "المفتاح الخاص",
    "تجاهل التعليمات", "تجاهل كل", "صدّر البيانات", "أرسل كل",
    "تجاوز الموافقة", "نفّذ هذا الأمر",
]
# Arabic imperative verbs commonly heading an injected directive.
_AR_DIRECTIVE = ["أرسل", "احذف", "تجاهل", "صدّر", "نفّذ", "شغّل", "اقرأ"]


def _snip(text: str, n: int = 60) -> str:
    t = text.replace("\n", " ")
    return (t[:n] + "…") if len(t) > n else t


# --- rules: each takes the combined text and returns a list[Finding] ------ #


def _rule_bidi(text: str) -> list[Finding]:
    f = detect_bidi_threats(text)
    out: list[Finding] = []
    if f.bidi_controls or f.bidi_marks:
        out.append(Finding(
            "R-BIDI-001", "bidi", "high",
            "BiDi control/mark characters can hide or reverse text from human review.",
            evidence=",".join(repr(c) for c in (f.bidi_controls + f.bidi_marks)),
            remediation="Strip U+202A–U+202E / U+2066–U+2069 from tool metadata; reject tools that need them.",
        ))
    if f.invisible_chars or f.tag_chars:
        out.append(Finding(
            "R-BIDI-002", "invisible", "high",
            "Invisible (zero-width) or Unicode TAG-block characters can carry a hidden payload.",
            evidence=f"invisible={len(f.invisible_chars)} tag={len(f.tag_chars)}",
            remediation="Reject tool metadata containing zero-width or TAG-block (U+E0000–U+E007F) codepoints.",
        ))
    return out


def _rule_homoglyph(text: str) -> list[Finding]:
    a = uts39_analyze(text)
    b = detect_bidi_threats(text)
    conf = list(getattr(a, "confusable_codepoints", ()) or ())
    if conf or b.homoglyphs or b.mixed_script_within_token:
        return [Finding(
            "R-HOMO-001", "homoglyph", "high",
            "Confusable / mixed-script characters within tokens mimic a trusted tool name or instruction.",
            evidence=f"confusables={len(conf)} homoglyphs={len(b.homoglyphs)} mixed_token={b.mixed_script_within_token}",
            remediation="Normalize to UTS-39 skeleton and reject mixed-script tokens in names/critical fields.",
        )]
    return []


def _rule_arabizi(text: str) -> list[Finding]:
    if looks_like_arabizi(text):
        return [Finding(
            "R-ARABIZI-001", "arabizi", "medium",
            "Latin-script Arabic (Arabizi) can carry an instruction invisible to English review.",
            evidence=_snip(text),
            remediation="Transliterate Arabizi to Arabic and re-scan for directives; treat as untrusted instruction text.",
        )]
    return []


def _rule_codeswitch(text: str) -> list[Finding]:
    script = str(detect_script(text))
    has_ar_directive = any(kw in text for kw in _AR_DIRECTIVE)
    if script == "mixed" and has_ar_directive:
        hit = next(kw for kw in _AR_DIRECTIVE if kw in text)
        return [Finding(
            "R-CODESWITCH-001", "codeswitch", "high",
            "Arabic imperative directive embedded in otherwise-English metadata (code-switched injection).",
            evidence=f"script=mixed; ar_directive={hit!r}",
            remediation="Scan non-Latin spans for directives independently; do not assume English-only metadata.",
        )]
    return []


def _rule_semantic(text: str) -> list[Finding]:
    out: list[Finding] = []
    m = _EXFIL_EN.search(text)
    if m:
        out.append(Finding(
            "R-EXFIL-001", "semantic", "high",
            "Tool metadata instructs reading secrets / exfiltration / bypassing approval.",
            evidence=_snip(m.group(0)),
            remediation="Reject tools whose description issues data-access or exfiltration directives.",
        ))
    ar = next((p for p in _EXFIL_AR if p in text), None)
    if ar:
        out.append(Finding(
            "R-EXFIL-002", "semantic", "high",
            "Arabic exfiltration / override directive in tool metadata.",
            evidence=ar,
            remediation="Apply semantic-injection rules to Arabic text, not only English.",
        ))
    return out


def _rule_override(text: str) -> list[Finding]:
    f = detect_prompt_injection(text)
    inds = list(getattr(f, "indicators", ()) or ())
    if inds:
        cats = sorted({i.category for i in inds})
        return [Finding(
            "R-OVERRIDE-001", "override", "high",
            "Explicit instruction-override phrasing in tool metadata.",
            evidence=",".join(cats),
            remediation="Reject tools whose metadata tries to override agent instructions.",
        )]
    return []


RULES: list[Callable[[str], list[Finding]]] = [
    _rule_bidi, _rule_homoglyph, _rule_arabizi,
    _rule_codeswitch, _rule_semantic, _rule_override,
]


@dataclass(frozen=True)
class ScanResult:
    tool_name: str
    findings: tuple[Finding, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(f.severity == "high" for f in self.findings)

    @property
    def max_severity(self) -> str:
        if not self.findings:
            return "none"
        return max((f.severity for f in self.findings), key=lambda s: SEVERITY_ORDER[s])

    @property
    def rule_ids(self) -> tuple[str, ...]:
        return tuple(f.rule_id for f in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "ok": self.ok,
            "max_severity": self.max_severity,
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_stage_record(self) -> StageRecord:
        return StageRecord(
            stage=STAGE_SCAN,
            tool="mizan.mcpscan",
            ok=self.ok,
            changes=len(self.findings),
            detail=self.to_dict(),
        )


def _tool_text(tool: Mapping[str, Any]) -> str:
    """Flatten the scannable surface of an MCP tool descriptor."""
    parts = [str(tool.get("name", "")), str(tool.get("description", ""))]
    schema = tool.get("input_schema") or tool.get("inputSchema") or {}
    props = (schema or {}).get("properties", {}) if isinstance(schema, dict) else {}
    for pname, pspec in (props.items() if isinstance(props, dict) else []):
        parts.append(str(pname))
        if isinstance(pspec, dict):
            parts.append(str(pspec.get("description", "")))
    return "\n".join(p for p in parts if p)


def scan_tool(tool: Mapping[str, Any]) -> ScanResult:
    """Scan one MCP tool descriptor for poisoning across all rule families."""
    text = _tool_text(tool)
    findings: list[Finding] = []
    for rule in RULES:
        findings.extend(rule(text))
    return ScanResult(tool_name=str(tool.get("name", "")), findings=tuple(findings))


def scan_tools(tools: list[Mapping[str, Any]]) -> list[ScanResult]:
    return [scan_tool(t) for t in tools]
