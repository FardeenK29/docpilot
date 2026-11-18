"""Runtime settings. The presets let the cost/latency teardown measure one fix at a time."""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


@dataclass(frozen=True)
class Settings:
    name: str = "optimized"
    chat_model: str = "qwen2.5:3b"          # answers questions, fills tool arguments
    router_model: str = "qwen2.5:1.5b"      # only used when fallback="llm"
    embed_model: str = "nomic-embed-text"
    use_rule_router: bool = True            # skip the router LLM for obvious intents
    fallback: str = "gate"                  # no rule matched: "llm" asks router_model, "gate" uses the retrieval score
    topic_min_score: float = 0.62           # gate: below this similarity to the docs, treat as off-topic
    top_k: int = 4
    min_score: float | None = 0.62          # below this, abstain instead of guessing
    max_chunk_chars: int = 1200
    max_answer_tokens: int = 350
    num_ctx: int = 8192
    router_num_ctx: int = 2048              # Ollama reloads a model whenever num_ctx changes
    collection: str = "fastapi_docs"
    qdrant_path: str = str(DATA_DIR / "qdrant")
    tickets_path: str = str(DATA_DIR / "tickets.jsonl")
    ollama_url: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")


# v1 as first shipped: every request goes through the router LLM (the same 3B
# model as the answerer, but with a smaller context window), retrieval pulls 8
# chunks, nothing caps the answer length, and it never abstains.
BASELINE = Settings(name="baseline", router_model="qwen2.5:3b", use_rule_router=False,
                    top_k=8, min_score=None, max_answer_tokens=1024)
# Teardown steps, each adding one fix on top of the previous one:
STEP1_CTX = replace(BASELINE, name="step1_ctx", router_num_ctx=8192)          # stop the model reload thrash
# Step 2a (rejected): rules first, a 1.5B router model for the rest. Faster, but the eval showed it
# broke off-topic refusals and sent a docs question to the ticket tool.
STEP2_ROUTER = replace(STEP1_CTX, name="step2_router", use_rule_router=True, fallback="llm",
                       router_model="qwen2.5:1.5b", router_num_ctx=2048)
# Step 2b: rules first, then the top retrieval score decides on-topic vs off-topic. No router LLM.
STEP2_GATE = replace(STEP1_CTX, name="step2_gate", use_rule_router=True, fallback="gate")
OPTIMIZED = Settings()                                                        # + k=4, answer cap, abstain threshold
PRESETS = {p.name: p for p in (BASELINE, STEP1_CTX, STEP2_ROUTER, STEP2_GATE, OPTIMIZED)}


def get_settings(preset: str | None = None, **overrides) -> Settings:
    base = PRESETS[preset or os.getenv("DOCPILOT_PRESET", "optimized")]
    return replace(base, **overrides) if overrides else base
