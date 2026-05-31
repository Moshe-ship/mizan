"""Evaluate mizan.mcpscan on the HELD-OUT adversarial corpus.

Reports generalization honestly: recall on poison (with the exact misses
listed), and false positives on clean tools (with the exact FPs listed).
Distinguishes hard-FP (a high finding on a clean tool) from advisory (medium).

Run:  python held_out.py && python held_out_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path.home() / "Projects" / "mizan"))

from mizan import scan_tool  # noqa: E402


def main() -> None:
    fname = sys.argv[1] if len(sys.argv) > 1 else "held_out.jsonl"
    held = Path(__file__).with_name(fname)
    cases = [json.loads(l) for l in held.read_text().splitlines() if l.strip()]
    print(f"[{fname}]")
    poison = [c for c in cases if c["label"] == "poison"]
    clean = [c for c in cases if c["label"] == "clean"]

    caught, missed = [], []
    for c in poison:
        res = scan_tool(c["tool"])
        (caught if res.findings else missed).append((c["id"], c["category"], res.rule_ids))

    hard_fp, advisory = [], []
    for c in clean:
        res = scan_tool(c["tool"])
        if not res.ok:                       # any HIGH finding
            hard_fp.append((c["id"], c["category"], res.rule_ids))
        elif res.findings:                   # only medium/low (advisory)
            advisory.append((c["id"], c["category"], res.rule_ids))

    print(f"=== HELD-OUT recall: {len(caught)}/{len(poison)} poison detected ===")
    for cid, cat, _ in caught:
        print(f"  caught {cid:7} {cat}")
    print("\n  MISSED (false negatives — generalization gaps):")
    for cid, cat, _ in missed:
        print(f"    MISS {cid:7} {cat}")

    print(f"\n=== false positives: {len(hard_fp)}/{len(clean)} clean tools flagged HIGH ===")
    for cid, cat, rules in hard_fp:
        print(f"    HARD-FP {cid:7} {cat}: {list(rules)}")
    print(f"\n  advisory (medium) on clean tools: {len(advisory)} (warn, not block)")
    for cid, cat, rules in advisory:
        print(f"    advisory {cid:7} {cat}: {list(rules)}")

    print(f"\nSUMMARY (held-out): recall {len(caught)}/{len(poison)} | "
          f"hard-FP {len(hard_fp)}/{len(clean)} | advisory {len(advisory)}/{len(clean)}")


if __name__ == "__main__":
    main()
