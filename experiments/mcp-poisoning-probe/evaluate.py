"""Evaluate mizan.mcpscan against the labeled corpus.

Reports recall (did the expected rule fire on each poisoned case) and the
false-positive rate (did any clean tool get flagged high). This is the
checker-as-eval artifact: every rule has positives and negatives.

Run:  python corpus.py && python evaluate.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path.home() / "Projects" / "mizan"))

from mizan import scan_tool  # noqa: E402

CORPUS = Path(__file__).with_name("corpus.jsonl")


def main() -> None:
    if not CORPUS.exists():
        print("corpus.jsonl missing — run: python corpus.py")
        return
    cases = [json.loads(l) for l in CORPUS.read_text().splitlines() if l.strip()]

    fam_total: dict[str, int] = defaultdict(int)
    fam_hit: dict[str, int] = defaultdict(int)
    rule_recall_total = rule_recall_hit = 0
    false_positives = []

    for c in cases:
        res = scan_tool(c["tool"])
        if c["label"] == "poison":
            fam_total[c["family"]] += 1
            # family recall: did ANY finding land (correct detection)
            if not res.ok or res.findings:
                fam_hit[c["family"]] += 1
            # exact-rule recall: did the *expected* rule fire
            rule_recall_total += 1
            if c["expect_rule"] in res.rule_ids:
                rule_recall_hit += 1
            elif not res.findings:
                print(f"  MISS {c['id']:10} ({c['family']}) expected {c['expect_rule']} — no finding")
        else:
            if not res.ok:  # any high finding on a clean tool == false positive
                false_positives.append((c["id"], c["tool"]["name"], res.rule_ids))

    print("\n=== recall by family (any detection) ===")
    for fam in sorted(fam_total):
        print(f"  {fam:11} {fam_hit[fam]}/{fam_total[fam]}")
    print(f"\nexact-rule recall: {rule_recall_hit}/{rule_recall_total}")

    clean = sum(c["label"] == "clean" for c in cases)
    print(f"false positives:   {len(false_positives)}/{clean} clean tools flagged high")
    for fid, name, rules in false_positives:
        print(f"    FP {fid} {name!r}: {list(rules)}")

    poison = sum(c["label"] == "poison" for c in cases)
    detected = sum(fam_hit.values())
    print(f"\nSUMMARY: detected {detected}/{poison} poison | exact-rule {rule_recall_hit}/{rule_recall_total} | "
          f"FP {len(false_positives)}/{clean}")


if __name__ == "__main__":
    main()
