"""Run the 50-item eval against one preset and write results/<preset>.json.

    python -m evals.run_eval --preset optimized
    python -m evals.run_eval --preset baseline

Quality is scored deterministically (no LLM judge): retrieval hit, citation
accuracy against the expected docs page, key-fact recall, and whether each
non-question item took the right route. Efficiency numbers (tokens, LLM calls,
latency) come from the AgentLens spans of each run. Traces are also exported
to the local collector, if one is running, so every eval run is in Jaeger.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import agentlens
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from docpilot.config import ROOT, get_settings
from docpilot.graph import build_graph

DATASET = Path(__file__).parent / "dataset.jsonl"
PII_STRINGS = ["ravi.k@example.com", "98765 43210"]
# Reference hosted price used to project cost from measured tokens (gpt-4o-mini list price, USD per 1M).
REF_PRICE_IN, REF_PRICE_OUT = 0.15, 0.60


def providers(preset: str):
    resource = Resource.create({"service.name": "docpilot", "docpilot.preset": preset})
    memory = InMemorySpanExporter()
    tp = TracerProvider(resource=resource)
    tp.add_span_processor(SimpleSpanProcessor(memory))
    mp = MeterProvider(resource=resource)
    try:  # also ship to the AgentLens stack when it's up
        import urllib.request
        urllib.request.urlopen("http://localhost:4318", timeout=1)
    except Exception as e:
        reachable = "HTTP Error" in str(e)  # collector answers 404/405 on '/'
    else:
        reachable = True
    if reachable:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")))
        mp = MeterProvider(resource=resource, views=agentlens._views(), metric_readers=[
            PeriodicExportingMetricReader(OTLPMetricExporter(endpoint="http://localhost:4318/v1/metrics"), 5000)])
    return memory, tp, mp


def score(item: dict, out: dict) -> dict:
    kind, route = item["kind"], out.get("route")
    answer = out.get("answer", "")
    res: dict = {"route": route, "intent": out.get("intent")}
    retrieved = [d.metadata["page"] for d in out.get("docs", [])]
    cited = [c["page"] for c in out.get("citations", [])]
    res.update(retrieved_pages=retrieved, cited_pages=cited)
    if kind == "question":
        exp = set(item["expected_pages"])
        res["retrieval_hit"] = bool(exp & set(retrieved))
        res["answered"] = route == "answered"
        res["has_citation"] = bool(cited)
        res["citation_correct"] = bool(exp & set(cited))
        facts = item["key_facts"]
        res["key_fact_recall"] = sum(f.lower() in answer.lower() for f in facts) / len(facts)
        res["pass"] = res["answered"] and res["citation_correct"] and res["key_fact_recall"] >= 0.5
    elif kind == "unanswerable":
        res["pass"] = route in ("abstained", "refused")
    elif kind == "off_topic":
        res["pass"] = route == "refused"
    elif kind == "ticket":
        res["pass"] = route == "ticket"
    elif kind == "escalate":
        res["pass"] = route == "escalated"
    leaked = [s for s in PII_STRINGS if s in item["question"] and (s in answer or s in json.dumps(out.get("ticket") or {}))]
    res["pii_leaked"] = leaked
    return res


def usage_from_spans(spans) -> dict:
    chats = [s for s in spans if s.name.startswith("chat ")]
    return {
        "llm_calls": len(chats),
        "input_tokens": sum(s.attributes.get("gen_ai.usage.input_tokens", 0) for s in chats),
        "output_tokens": sum(s.attributes.get("gen_ai.usage.output_tokens", 0) for s in chats),
        "models": sorted({s.attributes.get("gen_ai.request.model") for s in chats}),
    }


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, round(q * (len(values) - 1)))]


def summarize(rows: list[dict]) -> dict:
    qs = [r for r in rows if r["kind"] == "question"]
    by = lambda k: [r for r in rows if r["kind"] == k]  # noqa: E731
    lat = [r["latency_s"] for r in rows]
    n = len(rows)
    tin = sum(r["input_tokens"] for r in rows)
    tout = sum(r["output_tokens"] for r in rows)
    mean = lambda xs: round(statistics.mean(xs), 3) if xs else None  # noqa: E731
    return {
        "items": n,
        "pass_rate": mean([r["pass"] for r in rows]),
        "quality": {
            "retrieval_hit_rate": mean([r["retrieval_hit"] for r in qs]),
            "answered_rate": mean([r["answered"] for r in qs]),
            "citation_rate": mean([r["has_citation"] for r in qs]),
            "citation_accuracy": mean([r["citation_correct"] for r in qs]),
            "key_fact_recall": mean([r["key_fact_recall"] for r in qs]),
            "question_pass_rate": mean([r["pass"] for r in qs]),
            "abstain_on_unanswerable": mean([r["pass"] for r in by("unanswerable")]),
            "refuse_off_topic": mean([r["pass"] for r in by("off_topic")]),
            "action_routing": mean([r["pass"] for r in by("ticket") + by("escalate")]),
            "pii_leaks": sum(len(r["pii_leaked"]) for r in rows),
        },
        "efficiency": {
            "latency_p50_s": round(pct(lat, 0.5), 2),
            "latency_p95_s": round(pct(lat, 0.95), 2),
            "latency_mean_s": round(statistics.mean(lat), 2),
            "llm_calls_per_query": round(sum(r["llm_calls"] for r in rows) / n, 2),
            "input_tokens_per_query": round(tin / n),
            "output_tokens_per_query": round(tout / n),
            "projected_usd_per_1k_queries": round((tin * REF_PRICE_IN + tout * REF_PRICE_OUT) / 1e6 / n * 1000, 4),
            "projection_basis": f"measured tokens x ${REF_PRICE_IN}/${REF_PRICE_OUT} per 1M in/out",
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="optimized")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    settings = get_settings(args.preset)
    memory, tp, mp = providers(args.preset)
    app = agentlens.instrument(build_graph(settings), agent_name=f"docpilot-{args.preset}",
                               capture_content=True, tracer_provider=tp, meter_provider=mp)
    items = [json.loads(line) for line in DATASET.read_text().splitlines()][: args.limit]

    # Warm-up so model load time isn't charged to the first item.
    app.invoke({"question": "How do I declare a path parameter?"})
    app.invoke({"question": "Tell me a joke about cats"})
    memory.clear()

    rows = []
    for item in items:
        t = time.perf_counter()
        out = app.invoke({"question": item["question"]}, config={"configurable": {"thread_id": f"eval-{item['id']}"}})
        latency = time.perf_counter() - t
        row = {"id": item["id"], "kind": item["kind"], "question": item["question"], "latency_s": round(latency, 2),
               **usage_from_spans(memory.get_finished_spans()), **score(item, out), "answer": out.get("answer", "")}
        memory.clear()
        rows.append(row)
        mark = "PASS" if row["pass"] else "fail"
        print(f"[{item['id']:2d}] {mark} {latency:5.1f}s {row['llm_calls']} calls {row['input_tokens']:5d} in "
              f"{row['route']:9s} {item['question'][:60]}", flush=True)

    portable = {k: (str(Path(v).relative_to(ROOT)) if isinstance(v, str) and v.startswith(str(ROOT)) else v)
                for k, v in settings.__dict__.items()}
    summary = {"preset": args.preset, "settings": portable, "summary": summarize(rows), "rows": rows}
    out_path = ROOT / "results" / f"{args.preset}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps(summary["summary"], indent=2))
    tp.shutdown()
    mp.shutdown()


if __name__ == "__main__":
    main()
