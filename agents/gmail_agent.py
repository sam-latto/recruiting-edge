"""
Gmail Tracker Agent — scans Gmail for job application confirmation emails and
extracts structured application data.

Does NOT: write to the database, decide which results to persist, or deduplicate.
It returns a list of detected applications and lets the caller handle persistence.
Deduplication logic lives in db/database.py (application_exists()), not here.

Hands off to: the caller (pages/tracker.py or scheduler/gmail_scheduler.py),
which calls application_exists() before writing each detected application to
avoid creating duplicates.

Architecture note: The agent is stateless and receives a fully authenticated
gmail_service object — it never handles OAuth directly. This keeps the agent
testable with any mock service object.

Interview-ready design decision: The agent does not write to the DB directly.
It returns a list and lets the caller decide what to persist. This means the
same agent can be used by both the daily scheduler (which runs silently in the
background) and the UI (which shows the user a confirmation before saving).
"""

import base64
import email as email_lib
from datetime import datetime, timedelta, timezone
from typing import Any

import anthropic
from anthropic import Anthropic

from tools.gmail_client import fetch_messages

client = Anthropic()

MODEL = "claude-sonnet-4-6"

# Gmail search terms that reliably surface application confirmation emails
_CONFIRMATION_KEYWORDS = [
    "application received",
    "thank you for applying",
    "we received your application",
    "application submitted",
    "thanks for your interest",
    "successfully submitted",
]

_SYSTEM_PROMPT = """You are parsing a job application confirmation email to extract \
structured data. The email may be an automated confirmation from an ATS (Workday, \
Greenhouse, Lever, etc.) or a manual reply.

Extract:
- company: the company the candidate applied to (not the ATS vendor)
- role: the exact job title as written in the email
- date_applied: the date of the email in YYYY-MM-DD format

If a field is genuinely absent, use null. Do not guess.

Call the `submit_application` tool with your extraction."""

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "submit_application",
        "description": "Submit the structured application data extracted from the email.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": ["string", "null"]},
                "role": {"type": ["string", "null"]},
                "date_applied": {
                    "type": ["string", "null"],
                    "description": "YYYY-MM-DD format.",
                },
            },
            "required": ["company", "role", "date_applied"],
        },
    }
]


def _build_query(lookback_days: int) -> str:
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    date_str = cutoff.strftime("%Y/%m/%d")
    keyword_clause = " OR ".join(f'"{kw}"' for kw in _CONFIRMATION_KEYWORDS)
    return f"({keyword_clause}) after:{date_str}"


def _extract_from_email(message: dict) -> dict[str, Any] | None:
    """
    Send one email message to Claude and extract application details.
    Returns None if extraction fails or the email doesn't look like a confirmation.
    """
    content = f"Subject: {message['subject']}\nFrom: {message['from']}\nDate: {message['date']}\n\n{message['snippet']}"

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            tools=_TOOLS,
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": content}],
        )
    except anthropic.APIError:
        return None

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_application":
            data = block.input
            if not data.get("company") or not data.get("role"):
                return None
            return {
                "company": data["company"],
                "role": data["role"],
                "date_applied": data.get("date_applied"),
                "email_subject": message["subject"],
                "email_id": message["id"],
            }

    return None


def run_gmail_agent(
    gmail_service,
    user_id: str,
    lookback_days: int = 7,
) -> list[dict[str, Any]]:
    """
    Scan Gmail for job application confirmation emails and return structured data.

    Args:
        gmail_service: Authenticated Gmail API service from gmail_client.get_gmail_service().
        user_id: RecruitingEdge user ID (passed through to output for the caller's use).
        lookback_days: How many days back to search. Defaults to 7.

    Returns:
        List of dicts, each with keys: company, role, date_applied,
        email_subject, email_id. Never raises — returns empty list on failure.
    """
    query = _build_query(lookback_days)

    try:
        messages = fetch_messages(gmail_service, query, max_results=50)
    except Exception:
        return []

    detected: list[dict[str, Any]] = []
    for msg in messages:
        result = _extract_from_email(msg)
        if result:
            detected.append(result)

    return detected
