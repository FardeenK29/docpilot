"""Compare two eval runs: writes results/comparison.md and results/comparison.html.

    python -m evals.compare baseline optimized
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from docpilot.config import ROOT

ROWS = [
    # (label, section, key, kind, better)
    ("Question pass rate", "quality", "question_pass_rate", "pct", "up"),
    ("Retrieval hit rate", "quality", "retrieval_hit_rate", "pct", "up"),
    ("Citation accuracy", "quality", "citation_accuracy", "pct", "up"),
    ("Key-fact recall", "quality", "key_fact_recall", "pct", "up"),
    ("Abstains on unanswerable", "quality", "abstain_on_unanswerable", "pct", "up"),
    ("Refuses off-topic", "quality", "refuse_off_topic", "pct", "up"),
    ("Ticket / escalation routing", "quality", "action_routing", "pct", "up"),
    ("PII leaks", "quality", "pii_leaks", "int", "down"),
    ("Latency p50", "efficiency", "latency_p50_s", "sec", "down"),
    ("Latency p95", "efficiency", "latency_p95_s", "sec", "down"),
    ("LLM calls / query", "efficiency", "llm_calls_per_query", "num", "down"),
    ("Input tokens / query", "efficiency", "input_tokens_per_query", "int", "down"),
    ("Output tokens / query", "efficiency", "output_tokens_per_query", "int", "down"),
    ("Projected $ / 1k queries", "efficiency", "projected_usd_per_1k_queries", "usd", "down"),
]


def fmt(v, kind):
    if v is None:
        return "n/a"
    return {"pct": f"{v * 100:.0f}%", "sec": f"{v:.1f} s", "usd": f"${v:.3f}", "int": f"{v:,.0f}",
            "num": f"{v:.2f}"}[kind]


def delta(a, b, kind, better):
    if a in (None, 0) or b is None:
        return "", ""
    if kind == "pct":
        d = (b - a) * 100
        txt = f"{d:+.0f} pts"
        good = (d >= 0) if better == "up" else (d <= 0)
        return (txt if abs(d) >= 0.5 else "same"), ("good" if good else "bad") if abs(d) >= 0.5 else ""
    change = (b - a) / a * 100
    good = (change <= 0) if better == "down" else (change >= 0)
    return f"{change:+.0f}%", ("good" if good else "bad") if abs(change) >= 1 else ""


REJECTED = {"step2_router"}  # measured and kept in the table, but not carried forward
LABELS = {"baseline": "v1 baseline", "step1_ctx": "+ fix ctx reload", "step2_router": "+ 1.5B router (rejected)",
          "step2_gate": "+ rules & score gate", "optimized": "+ k=4, cap, abstain"}


def main(*names: str) -> None:
    names = names or ("baseline", "step1_ctx", "step2_gate", "optimized")
    res = ROOT / "results"
    runs = [json.loads((res / f"{n}.json").read_text()) for n in names]
    first, last = runs[0], runs[-1]
    head = [LABELS.get(n, n) for n in names]
    lines = ["| Metric | " + " | ".join(head) + f" | {head[0]} → {head[-1]} |",
             "|---|" + "---:|" * (len(names) + 1)]
    html_rows = []
    for label, sec, key, kind, better in ROWS:
        vals = [r["summary"][sec].get(key) for r in runs]
        d, cls = delta(vals[0], vals[-1], kind, better)
        lines.append(f"| {label} | " + " | ".join(fmt(v, kind) for v in vals) + f" | {d} |")
        cells = []
        for name, v in zip(names, vals):
            c = "rej" if name in REJECTED else ""
            if sec == "quality" and v is not None and vals[0] is not None:
                worse = (v < vals[0] - 0.005) if better == "up" else (v > vals[0])
                c += " worse" if worse else ""
            cells.append(f"<td class='{c.strip()}'>{fmt(v, kind)}</td>")
        html_rows.append(f"<tr class='{sec}'><td>{label}</td>" + "".join(cells) + f"<td class='{cls}'>{d}</td></tr>")
    basis = first["summary"]["efficiency"]["projection_basis"]
    md = "\n".join(lines) + f"\n\n*Projected $ = {basis}. All runs use local Qwen2.5 models, which cost $0 to run.*\n"
    (res / "comparison.md").write_text(md)
    print(md)

    n = first["summary"]["items"]
    ths = "".join(f"<th class='{'rej' if n in REJECTED else ''}'>{h}</th>" for n, h in zip(names, head))
    html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:#0f1216;color:#e6e9ee;font:15px/1.4 -apple-system,BlinkMacSystemFont,Inter,sans-serif}}
.card{{width:1080px;padding:28px 32px}}
h1{{font-size:22px;margin:0 0 4px}} p{{color:#94a0ae;margin:0 0 18px;font-size:13px}}
table{{width:100%;border-collapse:collapse}} th,td{{padding:8px 10px;border-bottom:1px solid #262c35;text-align:right}}
th:first-child,td:first-child{{text-align:left}} th{{color:#94a0ae;font-weight:500;font-size:12px}}
tr.quality td:first-child{{color:#cfe9e7}} tr.efficiency td:first-child{{color:#e6e9ee}}
td.good{{color:#3cc2b9;font-weight:700}} td.bad{{color:#f0795a;font-weight:700}}
td:last-child{{border-left:1px solid #262c35}}
.rej{{background:#161a20;color:#7d8794}} td.worse{{color:#f0795a}} td.rej.worse{{color:#f0795a;font-weight:700}}
.foot{{margin-top:14px;color:#94a0ae;font-size:12px}}
</style></head><body><div class="card">
<h1>DocPilot cost &amp; latency teardown</h1>
<p>Same {n}-item eval set (38 docs questions, 4 unanswerable, 4 off-topic, 4 ticket/escalation), same 8 GB M1, each fix added on top of the previous one. The grey column was measured and rejected. Red = worse than v1.</p>
<table><tr><th>Metric</th>{ths}<th>v1 → final</th></tr>{''.join(html_rows)}</table>
<div class="foot">Projected $ = {basis}. Local Qwen2.5 models via Ollama; the runs themselves cost $0.</div>
</div></body></html>"""
    (res / "comparison.html").write_text(html)


if __name__ == "__main__":
    main(*sys.argv[1:])
