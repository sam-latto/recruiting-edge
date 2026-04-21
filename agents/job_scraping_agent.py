"""
Job Scraping Agent — extracts structured job details from a URL, raw text, or PDF.

Does NOT: raise exceptions on scraping failure, write to the database, or
interact with the user. It returns a dict with scrape_success and fallback_needed
flags so the caller can decide how to respond.

Hands off to: the caller (pages/job_manager.py), which writes to
db/database.py and later passes job_details to tailoring_agent.py.

Architecture note: The agent never touches the network directly for URL sources —
it delegates to tools/web_scraper.py first and receives the extracted text.
This keeps the agent testable with any pre-fetched text, regardless of source type.

Interview-ready design decision: Web scraping fails silently and often.
Rather than letting an exception bubble up to the UI, this agent sets
scrape_success=False and fallback_needed=True so the UI always has a clear
path forward (prompt the user to paste the JD manually). The agent is never
the source of an unhandled error.
"""

import json
from typing import Any, Literal

import anthropic
from anthropic import Anthropic

from tools.pdf_parser import extract_text_from_pdf_path
from tools.web_scraper import scrape_url

client = Anthropic()

MODEL = "claude-sonnet-4-6"

SourceType = Literal["url", "text", "pdf"]

_SYSTEM_PROMPT = """You are a job description parser. You will receive raw text from \
a job posting and extract structured information from it.

Call the `submit_job_details` tool with the fields you extract. Be precise:
- required_skills: only skills explicitly listed as required/must-have
- preferred_skills: skills listed as preferred, nice-to-have, or bonus
- role_type: the functional category (e.g. "Product Manager", "Software Engineer", \
"Management Consultant", "Data Analyst")
- If a field is genuinely absent from the text, use null for optional fields or \
an empty list for list fields. Do not guess.
- description: a 2-4 sentence summary of the role and what it involves."""

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "submit_job_details",
        "description": "Submit the structured job details extracted from the posting.",
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "role": {"type": "string"},
                "role_type": {"type": "string"},
                "description": {"type": "string"},
                "required_skills": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "preferred_skills": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "location": {"type": ["string", "null"]},
            },
            "required": [
                "company", "role", "role_type", "description",
                "required_skills", "preferred_skills",
            ],
        },
    }
]

_FALLBACK: dict[str, Any] = {
    "company": "",
    "role": "",
    "role_type": "",
    "description": "",
    "required_skills": [],
    "preferred_skills": [],
    "location": None,
    "scrape_success": False,
    "fallback_needed": True,
}


def run_job_scraping_agent(
    source: str,
    source_type: SourceType,
) -> dict[str, Any]:
    """
    Extract structured job details from a URL, raw JD text, or PDF path.

    Args:
        source: A URL string, raw JD text, or file path to a PDF.
        source_type: One of "url", "text", or "pdf".

    Returns:
        Dict with keys: company, role, role_type, description, required_skills,
        preferred_skills, location, scrape_success, fallback_needed.
        Never raises — returns fallback dict on any failure.
    """
    # --- Step 1: Get raw text from the source ---
    raw_text = ""
    scrape_success = True

    if source_type == "url":
        raw_text, scrape_success = scrape_url(source)
        if not scrape_success or not raw_text.strip():
            return {**_FALLBACK, "scrape_success": False, "fallback_needed": True}

    elif source_type == "text":
        raw_text = source.strip()
        if not raw_text:
            return {**_FALLBACK, "scrape_success": False, "fallback_needed": True}

    elif source_type == "pdf":
        try:
            raw_text = extract_text_from_pdf_path(source)
            if not raw_text.strip():
                return {**_FALLBACK, "scrape_success": False, "fallback_needed": True}
        except ValueError:
            return {**_FALLBACK, "scrape_success": False, "fallback_needed": True}

    # --- Step 2: Send to Claude for structured extraction ---
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            tools=_TOOLS,
            tool_choice={"type": "any"},  # force a tool call
            messages=[
                {
                    "role": "user",
                    "content": f"Extract the job details from this posting:\n\n{raw_text}",
                }
            ],
        )
    except anthropic.APIError:
        return {**_FALLBACK, "scrape_success": scrape_success, "fallback_needed": True}

    # --- Step 3: Pull the tool result ---
    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_job_details":
            result = dict(block.input)
            result["scrape_success"] = scrape_success
            result["fallback_needed"] = False
            # Ensure list fields are lists even if the model returned None
            result.setdefault("required_skills", [])
            result.setdefault("preferred_skills", [])
            if result["required_skills"] is None:
                result["required_skills"] = []
            if result["preferred_skills"] is None:
                result["preferred_skills"] = []
            return result

    # No tool call returned — treat as failure
    return {**_FALLBACK, "scrape_success": scrape_success, "fallback_needed": True}
