"""Cheap, deterministic guardrails that run before any model sees the text."""

from __future__ import annotations

import re

_PII = [
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("API_KEY", re.compile(r"\b(?:sk|pk|ghp|gho|xox[abp]|AKIA)[-_A-Za-z0-9]{12,}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("AADHAAR", re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")),
    ("PHONE", re.compile(r"(?:\+\d{1,3}[\s-]?)?\b(?:\d{5}[\s-]?\d{5}|\d{3}[\s-]?\d{3}[\s-]?\d{4})\b")),
]


def redact(text: str) -> tuple[str, list[str]]:
    """Replace personal data with placeholders. Returns (clean_text, kinds_found)."""
    found = []
    for kind, pattern in _PII:
        text, n = pattern.subn(f"[{kind}]", text)
        if n:
            found.append(kind)
    return text, found


_TICKET = re.compile(r"\b(open|create|raise|file|log)\b.{0,20}\b(ticket|issue|bug report)\b|\breport (a|this) bug\b", re.I)
_HUMAN = re.compile(r"\b(human|real person|agent|someone|manager|support team)\b.{0,30}\b(talk|speak|connect|escalate|call)\b|"
                    r"\b(talk|speak|connect|escalate)\b.{0,30}\b(human|real person|someone|manager|support team)\b|"
                    r"\b(get|need|want)\b.{0,15}\b(a human|real person|your manager|a supervisor)\b", re.I)
_ON_TOPIC = re.compile(
    r"\b(fastapi|pydantic|starlette|uvicorn|endpoint|path operation|query param|request body|response model|"
    r"depend(s|ency|encies)|oauth2?|jwt|middleware|cors|websocket|background task|api ?router|openapi|swagger|"
    r"docker|deploy|https|async|await|header|cookie|form data|upload(ed|ing)?( files?)?|uploadfile|static files|status code|exception|validation|"
    r"lifespan|sql|database|test(s|ing)?client|settings|env(ironment)? var|template|static files|"
    r"http|api|route|routing|server|python type)\b", re.I)


def rule_intent(text: str) -> str | None:
    """Fast path for obvious intents; None means 'ask the router model'."""
    if _TICKET.search(text):
        return "ticket"
    if _HUMAN.search(text):
        return "escalate"
    if _ON_TOPIC.search(text):
        return "question"
    return None
