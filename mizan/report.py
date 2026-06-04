"""``mizan report`` — render a self-contained HTML report of a signed receipt log.

People read a table faster than JSONL. Given a hash-chained receipt log
(``mizan.chain.ReceiptLog``), this produces one standalone ``.html`` file (no
JS, no external assets) showing, per action: session, tool, decision, reason,
signature validity, claim verdict — plus a banner for chain integrity.

    mizan report receipts.jsonl [--secret-env MIZAN_RECEIPT_SECRET]
                               [--public-key key.json] [--out report.html]
"""

from __future__ import annotations

import html as _html
import json
import os
from typing import Any, Optional

from mizan import receipt_v0
from mizan.chain import verify_log

# status -> (label, css class)
_SIG = {
    receipt_v0.OK: ("VALID", "ok"),
    receipt_v0.TAMPERED: ("TAMPERED", "bad"),
    receipt_v0.UNSIGNED: ("unsigned", "warn"),
    receipt_v0.NO_SECRET: ("signed (no key)", "warn"),
    receipt_v0.INVALID: ("invalid", "bad"),
}
_VERIF = {
    "verified": ("matched", "ok"),
    "tampered": ("MISMATCH", "bad"),
    "unverified": ("unverified", "warn"),
    "not_applicable": ("—", "dim"),
}


def _receipts(path: str) -> list[dict[str, Any]]:
    """Yield receipt dicts from a chain log (or a bare-receipt JSONL)."""
    out: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            out.append(obj.get("receipt", obj))
    return out


def _decision(rec: dict) -> tuple[str, str, str]:
    """(action, css class, reason)."""
    dec = rec.get("decision") or {}
    action = str(dec.get("action") or "—")
    cls = {"allowed": "ok", "allow": "ok", "blocked": "bad", "block": "bad"}.get(action, "dim")
    return action, cls, str(dec.get("reason") or "")


def _pill(label: str, cls: str) -> str:
    return f'<span class="pill {cls}">{_html.escape(label)}</span>'


def render_html(path: str, *, secret: Optional[str] = None,
                public_key: Optional[str] = None) -> str:
    receipts = _receipts(path)
    chain_ok, problems = verify_log(path)

    rows: list[str] = []
    n_signed = n_blocked = 0
    for i, rec in enumerate(receipts):
        subj = rec.get("subject") or {}
        sig = rec.get("signature") or {}
        status = receipt_v0.verify(rec, secret, public_key=public_key)
        sig_label, sig_cls = _SIG.get(status, (status, "dim"))
        if (sig.get("value")):
            n_signed += 1
        action, act_cls, reason = _decision(rec)
        if act_cls == "bad":
            n_blocked += 1
        v_label, v_cls = _VERIF.get(str(rec.get("verification")), (rec.get("verification") or "—", "dim"))
        tool = subj.get("tool") or next(
            (s.get("tool") for s in rec.get("stages") or [] if not s.get("ok")), "—") or "—"
        rows.append(
            "<tr>"
            f'<td class="num">{i}</td>'
            f'<td class="mono">{_html.escape(str(subj.get("run_id") or "—"))}</td>'
            f'<td class="mono">{_html.escape(str(tool))}</td>'
            f"<td>{_pill(action, act_cls)}</td>"
            f'<td class="reason">{_html.escape(reason)}</td>'
            f"<td>{_pill(sig_label, sig_cls)} "
            f'<span class="dim mono">{_html.escape(str(sig.get("algorithm") or ""))}</span></td>'
            f"<td>{_pill(v_label, v_cls)}</td>"
            f'<td class="mono dim">{_html.escape(str(rec.get("receipt_id") or ""))}</td>'
            "</tr>"
        )

    chain_banner = (
        f'<span class="pill ok">chain intact · {len(receipts)} link(s)</span>'
        if chain_ok else
        f'<span class="pill bad">chain BROKEN · {len(problems)} problem(s)</span>'
    )
    sig_mode = "Ed25519 (public key)" if public_key else ("HMAC-SHA256" if secret else "not checked")

    return _TEMPLATE.format(
        path=_html.escape(os.path.basename(path)),
        chain_banner=chain_banner,
        total=len(receipts),
        signed=n_signed,
        blocked=n_blocked,
        sig_mode=_html.escape(sig_mode),
        rows="\n".join(rows) or '<tr><td colspan="8" class="dim">no receipts</td></tr>',
        problems=("".join(f"<li>{_html.escape(p)}</li>" for p in problems)
                  if problems else "<li>none</li>"),
    )


def cmd_report(args: Any) -> int:
    secret = os.environ.get(getattr(args, "secret_env", "") or "") or None
    public_key = None
    if getattr(args, "public_key", None):
        # accept hex or a keygen JSON (reuse verify's reader)
        from mizan.verify import _read_public_key
        public_key = _read_public_key(args.public_key)
    try:
        out_html = render_html(args.log, secret=secret, public_key=public_key)
    except FileNotFoundError:
        print(f"✗ cannot read log: {args.log}")
        return 1
    out_path = getattr(args, "out", None) or (os.path.splitext(args.log)[0] + ".html")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(out_html)
    print(f"✓ wrote {out_path}")
    if getattr(args, "open", False):
        import webbrowser
        webbrowser.open("file://" + os.path.abspath(out_path))
    return 0


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mizan receipts — {path}</title>
<style>
  :root {{ --ink:#111317; --dim:#6b7280; --line:#e5e7eb; --accent:#0d9488;
           --ok:#0f7b3f; --okbg:#e7f6ec; --bad:#b42318; --badbg:#fdeceb;
           --warn:#8a6d00; --warnbg:#fbf3d9; }}
  * {{ box-sizing:border-box; }}
  body {{ font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
          color:var(--ink); margin:0; padding:40px; background:#fff; }}
  .mono {{ font-family:"SF Mono",Menlo,Consolas,monospace; font-size:12.5px; }}
  h1 {{ font-size:26px; margin:0 0 2px; letter-spacing:-.5px; }}
  h1 span {{ color:var(--accent); }}
  .sub {{ color:var(--dim); margin:0 0 22px; }}
  .stats {{ display:flex; gap:10px; flex-wrap:wrap; margin-bottom:22px; }}
  .stat {{ border:1px solid var(--line); border-radius:10px; padding:10px 16px; }}
  .stat b {{ display:block; font-size:22px; }}
  .stat span {{ color:var(--dim); font-size:12px; text-transform:uppercase; letter-spacing:.5px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13.5px; }}
  th,td {{ text-align:left; padding:9px 12px; border-bottom:1px solid var(--line); vertical-align:top; }}
  th {{ font-size:11px; text-transform:uppercase; letter-spacing:.5px; color:var(--dim); }}
  td.num {{ color:var(--dim); }}
  td.reason {{ color:var(--dim); max-width:280px; }}
  .dim {{ color:var(--dim); }}
  .pill {{ display:inline-block; padding:2px 9px; border-radius:999px; font-size:11.5px;
           font-weight:600; }}
  .pill.ok {{ color:var(--ok); background:var(--okbg); }}
  .pill.bad {{ color:var(--bad); background:var(--badbg); }}
  .pill.warn {{ color:var(--warn); background:var(--warnbg); }}
  .pill.dim {{ color:var(--dim); background:#f3f4f6; }}
  details {{ margin-top:24px; color:var(--dim); font-size:13px; }}
  footer {{ margin-top:28px; color:var(--dim); font-size:12px; }}
</style></head>
<body>
  <h1><span>Mizan</span> receipts</h1>
  <p class="sub">{path} · signatures: {sig_mode}</p>
  <div class="stats">
    <div class="stat"><b>{chain_banner}</b><span>integrity</span></div>
    <div class="stat"><b>{total}</b><span>actions</span></div>
    <div class="stat"><b>{signed}</b><span>signed</span></div>
    <div class="stat"><b>{blocked}</b><span>blocked</span></div>
  </div>
  <table>
    <thead><tr>
      <th>#</th><th>session</th><th>tool</th><th>decision</th><th>reason</th>
      <th>signature</th><th>claim</th><th>receipt id</th>
    </tr></thead>
    <tbody>
    {rows}
    </tbody>
  </table>
  <details><summary>chain problems</summary><ul>{problems}</ul></details>
  <footer>Generated by <code>mizan report</code> — every row is an independently
  verifiable Receipt v0. Re-check: <code>mizan verify-log {path}</code>.</footer>
</body></html>
"""
