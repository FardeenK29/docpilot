"""Support tools. Tickets go to a local JSONL file standing in for Zendesk/Jira."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool

from .config import get_settings


def _append(record: dict) -> None:
    path = Path(get_settings().tickets_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(record) + "\n")


@tool
def create_support_ticket(summary: str, severity: Literal["low", "medium", "high"] = "medium") -> dict:
    """Open a support ticket for a problem the docs can't solve. `summary` is one sentence describing the issue."""
    ticket = {"ticket_id": f"T-{uuid.uuid4().hex[:6].upper()}", "type": "ticket", "summary": summary.strip()[:300],
              "severity": severity, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _append(ticket)
    return ticket


@tool
def escalate_to_human(reason: str) -> dict:
    """Hand the conversation to a human support engineer. `reason` says why in one sentence."""
    record = {"ticket_id": f"H-{uuid.uuid4().hex[:6].upper()}", "type": "escalation", "reason": reason.strip()[:300],
              "eta": "within 4 business hours", "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    _append(record)
    return record
