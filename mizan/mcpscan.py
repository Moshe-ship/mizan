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
from dataclasses import dataclass, field, replace
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
    field: str = ""          # provenance: which surface (name/description/param:x/cross-field/normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "family": self.family,
            "severity": self.severity,
            "field": self.field,
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
# Arabic imperative verbs that head an injected directive, split by how
# dangerous the verb itself is. A dangerous verb in mixed-script metadata is
# high on its own; a "soft" verb (read) needs a danger signal nearby — else a
# legitimate "اقرأ الوثائق / read the docs" instruction would be blocked.
_AR_DIRECTIVE_DANGEROUS = ["أرسل", "احذف", "صدّر", "نفّذ", "شغّل", "تجاهل"]
_AR_DIRECTIVE_SOFT = ["اقرأ", "حمّل", "اعرض"]
_AR_DIRECTIVE = _AR_DIRECTIVE_DANGEROUS + _AR_DIRECTIVE_SOFT
# Danger signals that turn a soft directive into a real exfiltration concern.
_DANGER_SIGNAL = re.compile(
    r"https?://|\.ssh|id_rsa|secret|token|password|credential|/etc/|إلى\s+http|خارج|الخادم|endpoint",
    re.IGNORECASE,
)


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


# Zero-width joiner/non-joiner used to break up a word. These are legitimate
# in Arabic/Persian/Indic typography, so only flag when they sit *between
# Latin/ASCII letters* — where they have no legitimate use and are obfuscation.
_JOINERS = {"‌", "‍"}  # ZWNJ, ZWJ


def _is_latin_letter(c: str) -> bool:
    return c.isascii() and c.isalpha()


def _rule_zwnj(text: str) -> list[Finding]:
    for i, ch in enumerate(text):
        if ch in _JOINERS:
            prev = text[i - 1] if i > 0 else ""
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if _is_latin_letter(prev) and _is_latin_letter(nxt):
                return [Finding(
                    "R-ZWNJ-001", "invisible", "high",
                    "Zero-width joiner used to split a Latin-script word — obfuscation (no legitimate use between ASCII letters).",
                    evidence=f"{prev!r}{'U+%04X' % ord(ch)}{nxt!r}",
                    remediation="Strip ZWNJ/ZWJ (U+200C/U+200D) from Latin tokens in tool metadata. Leave Arabic/Persian text untouched.",
                )]
    return []


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
    if str(detect_script(text)) != "mixed":
        return []
    danger = bool(_DANGER_SIGNAL.search(text))
    dangerous_hit = next((kw for kw in _AR_DIRECTIVE_DANGEROUS if kw in text), None)
    soft_hit = next((kw for kw in _AR_DIRECTIVE_SOFT if kw in text), None)

    # Dangerous directive (send/delete/export/run/ignore), OR a soft directive
    # (read) paired with a danger signal (URL/secret/exfil target) → high.
    if dangerous_hit or (soft_hit and danger):
        hit = dangerous_hit or soft_hit
        return [Finding(
            "R-CODESWITCH-001", "codeswitch", "high",
            "Arabic exfiltration/destructive directive embedded in mixed-script metadata.",
            evidence=f"script=mixed; ar_directive={hit!r}; danger={danger}",
            remediation="Scan non-Latin spans for directives; do not assume English-only metadata.",
        )]
    # Soft directive with no danger signal (e.g. legitimate "read the docs") →
    # advisory only, so normal Arabic instructions are not blocked.
    if soft_hit:
        return [Finding(
            "R-CODESWITCH-002", "codeswitch", "medium",
            "Arabic imperative in mixed-script metadata, no exfiltration signal (advisory — likely legitimate).",
            evidence=f"script=mixed; soft_directive={soft_hit!r}",
            remediation="Review only; legitimate bilingual docs commonly contain Arabic imperatives.",
        )]
    return []


def _rule_semantic(text: str) -> list[Finding]:
    out: list[Finding] = []
    # Semantic phrasing is advisory (medium): regex cannot read intent or
    # negation ("does not read private keys"), so it warns for human/LLM
    # review rather than hard-blocking like the high-precision structural rules.
    m = _EXFIL_EN.search(text)
    if m:
        out.append(Finding(
            "R-EXFIL-001", "semantic", "medium",
            "Tool metadata appears to instruct reading secrets / exfiltration / bypassing approval (advisory — confirm intent).",
            evidence=_snip(m.group(0)),
            remediation="Review the tool: legitimate security tools may mention these terms. Confirm with an LLM classifier before blocking.",
        ))
    ar = next((p for p in _EXFIL_AR if p in text), None)
    if ar:
        out.append(Finding(
            "R-EXFIL-002", "semantic", "medium",
            "Arabic exfiltration / override phrasing in tool metadata (advisory — confirm intent).",
            evidence=ar,
            remediation="Apply semantic-injection review to Arabic text, not only English; confirm intent before blocking.",
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
    _rule_bidi, _rule_zwnj, _rule_homoglyph, _rule_arabizi,
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


@dataclass(frozen=True)
class ScanConfig:
    """How a host should act on findings.

    mode:
      - "audit": never blocks; findings are logged/recorded only.
      - "warn":  surfaces a warning (and receipt) but allows the tool.
      - "block": rejects when a finding's severity is in block_severities
                 or its rule is in deny_rules.
    allow_rules: rule IDs to ignore entirely (false-positive overrides).
    deny_rules:  rule IDs that always block (regardless of severity), in
                 block mode.
    """

    mode: str = "audit"
    block_severities: frozenset[str] = frozenset({"high"})
    allow_rules: frozenset[str] = frozenset()
    deny_rules: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Decision:
    action: str          # allow | warn | block
    reason: str
    findings: tuple[Finding, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "findings": [f.to_dict() for f in self.findings],
        }


def decide(result: "ScanResult", config: ScanConfig | None = None) -> Decision:
    """Map findings + config to an allow/warn/block decision.

    Behaviour is severity- and mode-driven, not just `result.ok` — so a host
    can run audit-first, then escalate to warn/block deliberately.
    """
    config = config or ScanConfig()
    effective = tuple(f for f in result.findings if f.rule_id not in config.allow_rules)
    if not effective:
        return Decision("allow", "no findings", ())

    blocking = tuple(
        f for f in effective
        if f.severity in config.block_severities or f.rule_id in config.deny_rules
    )
    if config.mode == "block" and blocking:
        ids = ",".join(sorted({f.rule_id for f in blocking}))
        return Decision("block", f"blocking findings: {ids}", effective)
    if config.mode in ("warn", "block"):
        return Decision("warn", f"{len(effective)} finding(s)", effective)
    return Decision("allow", f"audit: {len(effective)} finding(s) logged", effective)


def report(result: "ScanResult") -> str:
    """Human-readable scan report: rule, severity, evidence, remediation."""
    if not result.findings:
        return f"✓ {result.tool_name}: no findings"
    lines = [f"⚠ {result.tool_name}: {len(result.findings)} finding(s) [{result.max_severity}]"]
    for f in result.findings:
        lines.append(f"  [{f.severity:6}] {f.rule_id:16} {f.family}")
        lines.append(f"     {f.message}")
        lines.append(f"     evidence:    {f.evidence[:80]}")
        lines.append(f"     remediation: {f.remediation}")
    return "\n".join(lines)


def _fields(tool: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Scannable surfaces of an MCP tool, with provenance labels."""
    out = [("name", str(tool.get("name", ""))), ("description", str(tool.get("description", "")))]
    schema = tool.get("input_schema") or tool.get("inputSchema") or {}
    props = (schema or {}).get("properties", {}) if isinstance(schema, dict) else {}
    if isinstance(props, dict):
        for pname, pspec in props.items():
            desc = pspec.get("description", "") if isinstance(pspec, dict) else ""
            out.append((f"param:{pname}", f"{pname} {desc}".strip()))
    return [(n, t) for n, t in out if t]


# Spaced-out evasion ("i g n o r e   a l l"). Treat 2+ spaces as a word
# boundary and collapse runs of >=3 single-char tokens joined by single spaces.
_SPACED_RUN = re.compile(r"(?:\b\w ){2,}\b\w\b")


def _despace(text: str) -> str:
    # Treat ALL whitespace consistently: 2+ whitespace = word boundary
    # (protected), single whitespace (space/tab/etc.) = potential letter
    # separator. Multi-char tokens still act as word boundaries, so we never
    # merge real words.
    sentinel = "\x00"
    t = re.sub(r"\s{2,}", sentinel, text)
    t = re.sub(r"[^\S\n]", " ", t)  # remaining single whitespace -> space (keep newlines)
    t = _SPACED_RUN.sub(lambda m: m.group(0).replace(" ", ""), t)
    return t.replace(sentinel, " ")


def scan_tool(tool: Mapping[str, Any]) -> ScanResult:
    """Scan one MCP tool descriptor across all rule families.

    Three passes: (1) per-field with provenance; (2) holistic space-joined to
    catch payloads split *across* fields; (3) normalized (de-spaced) to catch
    whitespace evasion. Findings new in passes 2-3 are downgraded to medium
    (lower confidence) and tagged with their field provenance.
    """
    fields = _fields(tool)
    findings: list[Finding] = []
    fired: set[str] = set()

    # 1) per-field (high confidence, exact provenance)
    for fname, text in fields:
        for rule in RULES:
            for f in rule(text):
                findings.append(replace(f, field=fname))
                fired.add(f.rule_id)

    def _extra_pass(text: str, label: str) -> None:
        for rule in RULES:
            for f in rule(text):
                if f.rule_id not in fired:
                    sev = "medium" if f.severity == "high" else f.severity
                    findings.append(replace(f, field=label, severity=sev))
                    fired.add(f.rule_id)

    # 2) holistic cross-field
    holistic = " ".join(t for _, t in fields)
    _extra_pass(holistic, "cross-field")

    # 3) normalized (de-spaced) — only if it changed the text
    norm = _despace(holistic)
    if norm != holistic:
        _extra_pass(norm, "normalized")

    return ScanResult(tool_name=str(tool.get("name", "")), findings=tuple(findings))


def scan_tools(tools: list[Mapping[str, Any]]) -> list[ScanResult]:
    return [scan_tool(t) for t in tools]


def _main(argv: list[str] | None = None) -> int:
    """CLI: scan a JSON file of MCP tool descriptor(s).

    Accepts a single tool object, a list of tools, or an MCP-style
    {"tools": [...]} payload. Prints a report per tool and exits non-zero
    if any decision is "block" under the chosen mode (default: audit).
    """
    import argparse
    import json

    ap = argparse.ArgumentParser(prog="mizan.mcpscan", description="Scan MCP tool descriptors for poisoning.")
    ap.add_argument("path", help="JSON file: a tool, a list of tools, or {\"tools\": [...]}")
    ap.add_argument("--mode", choices=["audit", "warn", "block"], default="audit")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and "tools" in data:
        tools = data["tools"]
    elif isinstance(data, dict):
        tools = [data]
    else:
        tools = data

    cfg = ScanConfig(mode=args.mode)
    blocked = 0
    for t in tools:
        res = scan_tool(t)
        d = decide(res, cfg)
        print(report(res))
        print(f"  → decision[{args.mode}]: {d.action} ({d.reason})\n")
        if d.action == "block":
            blocked += 1
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(_main())
