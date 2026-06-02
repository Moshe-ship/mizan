"""Claim vs execution — prove the agent didn't lie about the result.

`mizan verify` proves a receipt is signed and untampered. This goes one step
further: it weighs what the agent *claims* it did against what Mizan *observed*.
Runs on a bare `pip install mizan` — no primitives needed.

    python examples/attest_claim.py
"""

from __future__ import annotations

import json

from mizan import receipt_v0
from mizan.adapters.openai import receipt_tool

SECRET = "demo-secret"


@receipt_tool(secret=SECRET, key_id="local")
def book_flight(city: str) -> dict:
    return {"pnr": "OK123", "city": city}


def main() -> None:
    # 1) The tool runs; Mizan records a signed *execution* receipt.
    book_flight("Riyadh")
    execution = book_flight.last_receipt
    print("execution recorded:", execution["execution"]["tool"],
          "status", execution["execution"]["observed_status"])

    # 2) The agent later reports what it did. Attest the claim against execution.
    honest = receipt_v0.attest(execution, claimed_tool="book_flight",
                               claimed_result={"pnr": "OK123", "city": "Riyadh"},
                               secret=SECRET, key_id="local")
    liar = receipt_v0.attest(execution, claimed_tool="book_flight",
                             claimed_result={"pnr": "REFUNDED-9999", "city": "Riyadh"},
                             secret=SECRET, key_id="local")

    for name, doc in [("honest", honest), ("lying", liar)]:
        path = f"/tmp/claim-{name}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)
        print(f"\n{name} agent → verification={doc['verification']!r}  ({path})")
        print(f"  MIZAN_RECEIPT_SECRET={SECRET} mizan verify {path}"
              + ("   # exit 0" if doc["verification"] == "verified" else "   # exit 5 (lied)"))

    print("\n`mizan verify` proves integrity AND that the claim matches execution —")
    print("a forged 'verified' on mismatched hashes is rejected (exit 1).")


if __name__ == "__main__":
    main()
