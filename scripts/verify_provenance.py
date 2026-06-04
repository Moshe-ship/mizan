"""Independently verify PyPI provenance for the whole Mizan stack.

For each package, fetch its files from PyPI and check that the PEP 740
attestation (provenance) exists for the wheel AND the sdist, and that the
publisher is the expected GitHub repo + workflow. Exit 0 if all pass.

    python scripts/verify_provenance.py

No install needed — uses only the standard library and the public PyPI API.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

# Every package publishes via the same Trusted Publishing workflow filename.
EXPECTED_WORKFLOW = "release.yml"

# package -> (version, expected GitHub "owner/repo")
STACK = {
    "mizan": ("0.1.22", "Moshe-ship/mizan"),
    "jabr": ("0.1.0", "Moshe-ship/jabr"),
    "muqabalah": ("0.1.0", "Moshe-ship/muqabalah"),
    "qadiya": ("0.1.0", "Moshe-ship/qadiya"),
    "mtg-guards": ("0.1.0", "Moshe-ship/mtg"),
    "toolproof-receipt": ("0.5.2", "Moshe-ship/toolproof"),
}


def _get_json(url: str):
    with urllib.request.urlopen(url, timeout=20) as r:
        return json.load(r)


def _provenance(name: str, version: str, filename: str):
    url = f"https://pypi.org/integrity/{name}/{version}/{filename}/provenance"
    try:
        return _get_json(url)
    except urllib.error.HTTPError as e:
        return {"_http": e.code}
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e)}


def main() -> int:
    ok = True
    for name, (version, repo) in STACK.items():
        try:
            files = [u["filename"] for u in _get_json(f"https://pypi.org/pypi/{name}/{version}/json")["urls"]]
        except Exception as e:  # noqa: BLE001
            print(f"✗ {name} {version}: cannot fetch files ({e})")
            ok = False
            continue
        has_whl = any(f.endswith(".whl") for f in files)
        has_sdist = any(f.endswith(".tar.gz") for f in files)
        if not (has_whl and has_sdist):
            print(f"✗ {name} {version}: missing wheel or sdist: {files}")
            ok = False
            continue
        problems = []
        for f in files:
            prov = _provenance(name, version, f)
            if "_http" in prov or "_error" in prov:
                problems.append(f"{f}: no provenance ({prov})")
                continue
            try:
                pub = prov["attestation_bundles"][0]["publisher"]
                if pub.get("repository") != repo:
                    problems.append(f"{f}: publisher repo {pub.get('repository')} != {repo}")
                if pub.get("workflow") != EXPECTED_WORKFLOW:
                    problems.append(f"{f}: workflow {pub.get('workflow')} != {EXPECTED_WORKFLOW}")
            except (KeyError, IndexError, TypeError):
                problems.append(f"{f}: malformed provenance")
        if problems:
            ok = False
            print(f"✗ {name} {version}: " + "; ".join(problems))
        else:
            print(f"✓ {name} {version}: wheel + sdist provenance OK "
                  f"(publisher {repo} · {EXPECTED_WORKFLOW})")
    print("\n" + ("ALL PROVENANCE VERIFIED" if ok else "PROVENANCE CHECK FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
