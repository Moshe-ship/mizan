"""`mizan` command-line entry point.

    mizan verify receipt.json [--secret-env MIZAN_RECEIPT_SECRET] [--allow-unsigned]
    mizan diff a.json b.json [--include-volatile]

The MCP scanner keeps its own entry point: `python -m mizan.mcpscan ...`.
"""

from __future__ import annotations

import argparse
from typing import Optional, Sequence


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="mizan", description="Mizan — signed evidence for agent actions.")
    sub = parser.add_subparsers(dest="command", required=True)

    pv = sub.add_parser("verify", help="validate and signature-check a receipt")
    pv.add_argument("receipt", help="path to a receipt JSON file")
    pv.add_argument(
        "--secret-env",
        default="MIZAN_RECEIPT_SECRET",
        help="env var holding the HMAC secret (default: MIZAN_RECEIPT_SECRET)",
    )
    pv.add_argument("--public-key", metavar="FILE",
                    help="public key (hex, or a keygen JSON) to verify an Ed25519 receipt")
    pv.add_argument("--allow-unsigned", action="store_true", help="exit 0 on a valid but unsigned receipt")
    pv.add_argument("--allow-claim-mismatch", action="store_true",
                    help="exit 0 even when the agent's claim does not match execution")

    pk = sub.add_parser("keygen", help="generate an Ed25519 keypair for signing receipts")
    pk.add_argument("--key-id", default=None, help="optional key identifier to embed")
    pk.add_argument("--out", metavar="FILE", help="write the keypair JSON here (else stdout)")

    pl = sub.add_parser("verify-log", help="verify a hash-chained, append-only receipt log")
    pl.add_argument("log", help="path to a JSONL receipt log (see mizan.chain.ReceiptLog)")
    pl.add_argument("--secret-env", default="MIZAN_RECEIPT_SECRET",
                    help="also verify each receipt's HMAC signature using this env var")
    pl.add_argument("--public-key", metavar="FILE",
                    help="also verify each receipt's Ed25519 signature with this public key")
    pl.add_argument("--expect-head", metavar="HEX",
                    help="anchored head digest — detects tail truncation/alteration")
    pl.add_argument("--expect-count", type=int, metavar="N",
                    help="anchored link count — detects tail truncation/extension")

    pd = sub.add_parser("diff", help="compare two receipts")
    pd.add_argument("a", help="path to receipt A")
    pd.add_argument("b", help="path to receipt B")
    pd.add_argument("--include-volatile", action="store_true", help="also compare receipt_id/created_at/signature")

    args = parser.parse_args(argv)

    from mizan.verify import cmd_diff, cmd_keygen, cmd_verify, cmd_verify_log

    if args.command == "verify":
        return cmd_verify(args)
    if args.command == "diff":
        return cmd_diff(args)
    if args.command == "keygen":
        return cmd_keygen(args)
    if args.command == "verify-log":
        return cmd_verify_log(args)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
