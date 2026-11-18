"""Fast unit tests (no model or vector DB needed)."""

from langchain_core.documents import Document

from docpilot.graph import extract_citations, format_sources
from docpilot.guardrails import redact, rule_intent


def _doc(page, n=1):
    return Document(page_content=f"text {n}", metadata={"title": f"T{n}", "heading": f"H{n}", "url": f"https://x/{page}", "page": page, "score": 0.8})


def test_redaction():
    text, found = redact("mail ravi.k@example.com or call +91 98765 43210, key sk-abcdefghijklmnop1234")
    assert "ravi.k@example.com" not in text and "98765" not in text and "sk-abc" not in text
    assert set(found) == {"EMAIL", "PHONE", "API_KEY"}


def test_redaction_leaves_versions_alone():
    assert redact("upgrade python 3.12 and fastapi 0.115.6")[1] == []


def test_rule_router():
    assert rule_intent("please open a ticket, uploads crash") == "ticket"
    assert rule_intent("can I speak to a human about billing") == "escalate"
    assert rule_intent("how do I add CORS middleware") == "question"
    assert rule_intent("best biryani recipe?") is None  # falls through to the topic gate
    assert rule_intent("can you help me file my income tax return?") is None  # "file" alone is not a FastAPI term
    assert rule_intent("this bot is useless, get me your manager") == "escalate"


def test_citations_are_validated_and_deduplicated():
    docs = [_doc("a.md", 1), _doc("b.md", 2)]
    cites = extract_citations("Use X [1][2]. Also [2] and a bogus [7].", docs)
    assert [c["page"] for c in cites] == ["a.md", "b.md"]


def test_sources_are_numbered():
    s = format_sources([_doc("a.md", 1), _doc("b.md", 2)])
    assert s.startswith("[1] T1 > H1") and "[2] T2 > H2" in s


def test_snippet_is_plain_text():
    from docpilot.graph import snippet
    s = snippet("## Use `X` { #use-x }\n\nCall **FastAPI** with `X`.\n\n```python\ncode()\n```\nSee [docs](https://x).")
    assert s == "Call FastAPI with X. See docs."
