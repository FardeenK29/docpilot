"""The DocPilot agent graph.

    guard ─► route ─┬─ question ─► retrieve ─┬─ generate (answer with [n] citations)
                    ├─ unsure ───┘            ├─ abstain  (weak retrieval: say so, offer a ticket)
                    │                         └─ refuse   (unsure + far from the docs: off-topic)
                    ├─ ticket ───► ticket     (LLM fills create_support_ticket args)
                    ├─ escalate ─► escalate   (escalate_to_human)
                    └─ off_topic ► refuse
"""

from __future__ import annotations

import json
import re
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_ollama import ChatOllama
from langgraph.graph import END, START, StateGraph

from .config import Settings, get_settings
from .guardrails import redact, rule_intent
from .retriever import DocsRetriever
from .tools import create_support_ticket, escalate_to_human

INTENTS = ("question", "ticket", "escalate", "off_topic")
NOT_FOUND = "I couldn't find that in the FastAPI docs."

ROUTER_PROMPT = """You route messages for a FastAPI documentation support bot.
Reply with JSON only: {"intent": "<one of: question, ticket, escalate, off_topic>"}
- question: asks how to do something with FastAPI, Python web APIs, or deploying them
- ticket: wants to open a ticket or report a bug
- escalate: wants a human
- off_topic: anything unrelated to FastAPI or building web APIs (recipes, sports, general chit-chat)"""

ANSWER_PROMPT = """You are DocPilot, a support assistant for the FastAPI web framework.
Answer the user's question using ONLY the numbered sources below.
- Cite every claim with the source number in square brackets, like [1] or [2][3].
- Be concise: 2-5 sentences, plus a short code snippet only if it really helps.
- If the sources do not contain the answer, reply exactly: "I couldn't find that in the FastAPI docs."

Sources:
{sources}"""


class State(TypedDict, total=False):
    question: str
    pii: list[str]
    intent: str
    docs: list[Document]
    answer: str
    citations: list[dict]
    route: str          # answered | abstained | refused | ticket | escalated
    ticket: dict | None


def format_sources(docs: list[Document]) -> str:
    return "\n\n".join(f"[{i}] {d.metadata['title']} > {d.metadata['heading']}\n{d.page_content}"
                       for i, d in enumerate(docs, 1))


def snippet(markdown: str) -> str:
    """Plain-text preview of a chunk: no code blocks, headings, anchors or markdown markup."""
    text = re.sub(r"```.*?```", " ", markdown, flags=re.S)
    text = re.sub(r"^\s*#+\s.*$", " ", text, flags=re.M)
    text = re.sub(r"\{\s*#[^}]*\}", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*|`|^\s*[-*]\s+|^\s*///\s*\w*", "", text, flags=re.M)
    text = re.sub(r"\s+", " ", text).strip()
    return text or re.sub(r"\s+", " ", markdown).strip()


def extract_citations(answer: str, docs: list[Document]) -> list[dict]:
    cited = []
    for n in dict.fromkeys(int(x) for x in re.findall(r"\[(\d+)\]", answer)):
        if 1 <= n <= len(docs):
            m = docs[n - 1].metadata
            text = snippet(docs[n - 1].page_content)
            cited.append({"n": n, "title": m["title"], "heading": m["heading"], "url": m["url"], "page": m["page"],
                          "score": round(float(m.get("score", 0.0)), 3),
                          "snippet": text[:280] + ("…" if len(text) > 280 else "")})
    return cited


def build_graph(settings: Settings | None = None):
    s = settings or get_settings()
    chat = ChatOllama(model=s.chat_model, base_url=s.ollama_url, temperature=0, num_ctx=s.num_ctx,
                      num_predict=s.max_answer_tokens)
    router = ChatOllama(model=s.router_model, base_url=s.ollama_url, temperature=0, num_ctx=s.router_num_ctx,
                        num_predict=24, format="json")
    retriever = DocsRetriever(qdrant_path=s.qdrant_path, collection=s.collection, embed_model=s.embed_model,
                              ollama_url=s.ollama_url, k=s.top_k, max_chunk_chars=s.max_chunk_chars)
    ticket_llm = chat.bind_tools([create_support_ticket])

    def guard(state: State) -> State:
        clean, found = redact(state["question"])
        return {"question": clean, "pii": found}

    def route(state: State, config: RunnableConfig) -> State:
        intent = rule_intent(state["question"]) if s.use_rule_router else None
        if intent is None and s.use_rule_router and s.fallback == "gate":
            intent = "unsure"   # decided after retrieval, by how close the message is to the docs
        if intent is None:
            raw = router.invoke([SystemMessage(ROUTER_PROMPT), HumanMessage(state["question"])], config).content
            try:
                intent = json.loads(raw).get("intent")
            except (json.JSONDecodeError, AttributeError):
                intent = None
            intent = intent if intent in INTENTS else "question"
        return {"intent": intent}

    def retrieve(state: State, config: RunnableConfig) -> State:
        return {"docs": retriever.invoke(state["question"], config)}

    def after_retrieve(state: State) -> str:
        docs = state["docs"]
        top = docs[0].metadata["score"] if docs else 0.0
        if state.get("intent") == "unsure" and top < s.topic_min_score:
            return "refuse"
        if s.min_score is not None and top < s.min_score:
            return "abstain"
        return "generate"

    def generate(state: State, config: RunnableConfig) -> State:
        docs = state["docs"]
        msg = chat.invoke([SystemMessage(ANSWER_PROMPT.format(sources=format_sources(docs))),
                           HumanMessage(f"{state['question']}\n\nAnswer using the sources above and cite them like [1].")],
                          config)
        answer = msg.content.strip()
        if NOT_FOUND.lower().rstrip(".") in answer.lower():
            return {"answer": NOT_FOUND + " Want me to open a support ticket?", "citations": [], "route": "abstained"}
        return {"answer": answer, "citations": extract_citations(answer, docs), "route": "answered"}

    def abstain(state: State) -> State:
        return {"answer": NOT_FOUND + " Want me to open a support ticket?", "citations": [], "route": "abstained"}

    def refuse(state: State) -> State:
        return {"answer": "I can only help with FastAPI and building APIs with it. What would you like to know?",
                "citations": [], "route": "refused"}

    def ticket(state: State, config: RunnableConfig) -> State:
        msg = ticket_llm.invoke([SystemMessage("Open a support ticket for the user's issue using the tool."),
                                 HumanMessage(state["question"])], config)
        call = next((c for c in msg.tool_calls if c["name"] == "create_support_ticket"), None)
        args = call["args"] if call else {"summary": state["question"], "severity": "medium"}
        if args.get("severity") not in ("low", "medium", "high"):
            args["severity"] = "medium"
        t = create_support_ticket.invoke({"summary": args.get("summary") or state["question"],
                                          "severity": args["severity"]}, config)
        return {"ticket": t, "route": "ticket", "citations": [],
                "answer": f"I've opened ticket {t['ticket_id']} ({t['severity']} priority): {t['summary']}"}

    def escalate(state: State, config: RunnableConfig) -> State:
        h = escalate_to_human.invoke({"reason": state["question"]}, config)
        return {"ticket": h, "route": "escalated", "citations": [],
                "answer": f"I've passed this to a human engineer (ref {h['ticket_id']}). They'll reply {h['eta']}."}

    g = StateGraph(State)
    for name, fn in [("guard", guard), ("route", route), ("retrieve", retrieve), ("generate", generate),
                     ("abstain", abstain), ("refuse", refuse), ("ticket", ticket), ("escalate", escalate)]:
        g.add_node(name, fn)
    g.add_edge(START, "guard")
    g.add_edge("guard", "route")
    g.add_conditional_edges("route", lambda st: st["intent"],
                            {"question": "retrieve", "unsure": "retrieve", "ticket": "ticket", "escalate": "escalate",
                             "off_topic": "refuse"})
    g.add_conditional_edges("retrieve", after_retrieve, {"generate": "generate", "abstain": "abstain", "refuse": "refuse"})
    for n in ("generate", "abstain", "refuse", "ticket", "escalate"):
        g.add_edge(n, END)
    return g.compile(name="docpilot")
