"""HTTP API and chat UI.

    uvicorn docpilot.api:app --port 8000
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import agentlens
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from opentelemetry import trace
from pydantic import BaseModel, Field

from .config import ROOT, get_settings
from .graph import build_graph
from .guardrails import redact

JAEGER_UI = os.getenv("JAEGER_UI", "http://localhost:16686")

agentlens.configure(service_name="docpilot-api")
settings = get_settings()
graph = agentlens.instrument(build_graph(settings), agent_name="docpilot")
tracer = trace.get_tracer("docpilot.api")

app = FastAPI(title="DocPilot", description="RAG support agent over the FastAPI docs")


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None


class Citation(BaseModel):
    n: int
    title: str
    heading: str
    url: str
    snippet: str = ""
    score: float | None = None


class ChatOut(BaseModel):
    answer: str
    route: str
    citations: list[Citation]
    ticket: dict | None = None
    redacted: list[str]
    redacted_message: str
    latency_ms: int
    trace_url: str


@app.post("/api/chat", response_model=ChatOut)
def chat(body: ChatIn) -> ChatOut:
    # Redact before anything (including traces) sees the text.
    message, found = redact(body.message)
    t = time.perf_counter()
    with tracer.start_as_current_span("docpilot.chat") as span:
        out = graph.invoke({"question": message},
                           config={"configurable": {"thread_id": body.session_id or "anonymous"}})
        trace_id = format(span.get_span_context().trace_id, "032x")
    return ChatOut(answer=out["answer"], route=out["route"], citations=out.get("citations", []),
                   ticket=out.get("ticket"), redacted=found, redacted_message=message, latency_ms=int((time.perf_counter() - t) * 1000),
                   trace_url=f"{JAEGER_UI}/trace/{trace_id}")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "preset": settings.name, "chat_model": settings.chat_model,
            "embed_model": settings.embed_model, "top_k": settings.top_k}


@app.get("/api/scorecard")
def scorecard() -> dict:
    """Summary of the latest eval run for the active preset (python -m evals.run_eval writes it)."""
    path = ROOT / "results" / f"{settings.name}.json"
    if not path.exists():
        raise HTTPException(404, f"No eval results for preset {settings.name!r} yet")
    data = json.loads(path.read_text())
    return {"preset": data["preset"], **data["summary"]}


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html", headers={"Cache-Control": "no-cache"})


@app.on_event("shutdown")
def _flush() -> None:
    agentlens.shutdown()
