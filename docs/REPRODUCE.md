# Reproduce every claim

We'd rather you check than trust. Every public claim about Mizan — the benchmark
numbers, the tests, the supply-chain provenance, the signed/verifiable receipts —
is reproducible from a clean machine in a few commands. If any of it is wrong,
that's the most useful bug report we can get.

```bash
git clone https://github.com/Moshe-ship/mizan && cd mizan
python -m venv .venv && . .venv/bin/activate
```

## 1. The scanner benchmark (no install needed)

`benchmark/run.py` adds the checkout to `sys.path`, so it runs straight from the
clone. It prints per-category catch/miss/false-positive and exits non-zero on a
regression.

```bash
python benchmark/run.py --check
```

Expected (current corpus): **consistency 25/25**, **held-out 16/16**, **0 hard
false positives**. The corpus is committed under [`benchmark/corpus/`](../benchmark/corpus/);
inspect or extend it. These are Mizan-only numbers — no competitor numbers are
claimed (see the benchmark doc's *Follow-up*).

## 2. The test suite

```bash
pip install -e ".[all,test,ed25519]"
python -m pytest -q
```

Expected: all tests pass (121 at time of writing), across Python 3.10–3.13 in CI.

## 3. PyPI provenance for the whole stack (stdlib only)

Confirm every package — mizan and the five primitives — was published by the
expected GitHub repo + workflow via Trusted Publishing, with a PEP 740
attestation on **both** the wheel and the sdist:

```bash
python scripts/verify_provenance.py
```

Expected: `ALL PROVENANCE VERIFIED`. Or check one by hand:

```bash
curl -s https://pypi.org/integrity/mizan/0.1.19/mizan-0.1.19-py3-none-any.whl/provenance \
  | python -c "import sys,json; b=json.load(sys.stdin)['attestation_bundles'][0]['publisher']; print(b['kind'], b['repository'], b['workflow'])"
# -> GitHub Moshe-ship/mizan release.yml
```

## 4. The end-to-end demo

```bash
python examples/full_pipeline_demo.py
```

You should see eight steps: a poisoned MCP tool flagged, a contradiction caught,
the tool gate, a transliteration blocked, a fake claim rejected, one signed
Receipt, `mizan verify` passing, and a tamper failing.

## 5. Receipts: verify, claim-vs-execution, Ed25519, hash chain

```bash
# build a signed receipt and verify it
python - <<'PY'
import json
from mizan.receipt import Receipt
json.dump(Receipt("hello","ok").to_v0(secret="s"), open("/tmp/r.json","w"))
PY
MIZAN_RECEIPT_SECRET=s mizan verify /tmp/r.json        # exit 0
python -c "import json;d=json.load(open('/tmp/r.json'));d['output']['hash']='sha256:'+'0'*64;json.dump(d,open('/tmp/r.json','w'))"
MIZAN_RECEIPT_SECRET=s mizan verify /tmp/r.json; echo "exit=$?"   # exit 2 (tampered)

# Ed25519: verify with the public key only
mizan keygen --out /tmp/key.json
python - <<'PY'
import json
from mizan.receipt import Receipt
from mizan.signing import Ed25519Signer
kp=json.load(open("/tmp/key.json"))
doc=Receipt("x","ok").to_v0(signer=Ed25519Signer(kp["private_key"], key_id=kp["key_id"]))
json.dump(doc, open("/tmp/ed.json","w"))
PY
mizan verify /tmp/ed.json --public-key /tmp/key.json   # exit 0, no private key used

# hash-chained audit log + tamper
python examples/audit_log.py
```

## 6. What you should NOT be able to reproduce

These are the honesty boundaries — if you *can* do any of them, that's a real bug:

- A receipt that says `verification: verified` while its hashes don't match,
  passing `mizan verify` (it must exit `1`).
- A modified/forged receipt passing the signature check.
- A reordered or middle-deleted entry in a chained log passing `mizan verify-log`.
- The scanner producing a **high-severity** finding on any item in
  `benchmark/corpus/clean.jsonl`.

Find one and open an issue — that's exactly the feedback this project wants.
