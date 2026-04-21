"""
Resume Bullet Tailoring Agent — leads a back-and-forth conversation to rewrite
a single resume bullet for a specific job posting.

Does NOT: write to the database, produce a formatted resume, or generate
generic rewrites without first establishing which skill to demonstrate.

Hands off to: the caller (pages/tailoring.py), which writes accepted bullets
to db/database.py (tailored_bullets table) and later surfaces them to the user.

Architecture note: This is the central agent of the product. It is
intentionally conversational rather than one-shot. The conversation loop
forces the user to (1) confirm which skill they want to demonstrate and
(2) verify that the proposed rewrite reflects their real experience. The
story bank integration is what makes this possible — if a STAR story exists
for this bullet, the agent references specific results from that story rather
than inventing numbers.

Interview-ready design decision: Why not one-shot? One-shot rewrites produce
polished-sounding but often factually thin bullets. The conversational loop
surfaces the user's real details and keeps the agent honest about what it
actually knows vs. what it's making up.
"""

# HOOK: Custom resume agent
# When the custom agent is ready, import it here and route
# the rewrite step through it instead of the raw Anthropic call.
# The agent should accept (bullet, job_details, skill, story_context)
# and return a proposed bullet string.
USE_CUSTOM_RESUME_AGENT = False  # Flip to True when agent is ready

import json
from typing import Any

import anthropic
from anthropic import Anthropic

client = Anthropic()

MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are a career coach helping an MBA student rewrite a single \
resume bullet to better match a specific job posting.

Your process — follow this order:
1. If this is the first message, read the bullet and the job details. Ask the \
student which skill or theme from the job description they most want this bullet \
to demonstrate. Give them 2-3 options drawn from the required skills list.
2. Once you know the target skill, check the story bank. If a STAR story exists \
for this bullet, anchor your rewrite to specific details from that story (numbers, \
outcomes, stakeholders). Never invent details.
3. Propose a rewrite. Use strong action verbs, quantify impact, and weave in the \
target skill naturally — do not keyword-stuff.
4. Invite feedback. If the student wants changes, revise. Repeat until they accept.
5. When the student accepts ("looks good", "save it", "that's the one", "yes"), \
call the `finalize_bullet` tool with the accepted bullet and the target skill.

Rules:
- Never produce a formatted resume. Bullets only.
- Do not propose a rewrite before knowing the target skill.
- If no STAR story exists for this bullet, say so and ask the student to provide \
the key detail or number you should use.
- Keep rewrites to one sentence. Action verb → task/scope → quantified result.
- If the student wants to start over with a different bullet, that is fine — \
just acknowledge it and wait for the new bullet from the UI."""

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "finalize_bullet",
        "description": (
            "Call this tool when the student has explicitly accepted a proposed "
            "rewrite. Captures the final bullet and the skill it demonstrates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "proposed_bullet": {
                    "type": "string",
                    "description": "The exact bullet text the student accepted.",
                },
                "target_skill": {
                    "type": "string",
                    "description": "The skill or theme this bullet is optimized for.",
                },
            },
            "required": ["proposed_bullet", "target_skill"],
        },
    }
]


def _build_context_block(
    bullet: str,
    job_details: dict[str, Any],
    story_bank: list[dict[str, Any]],
) -> str:
    """Build the static context injected into the system prompt on each turn."""
    req_skills = ", ".join(job_details.get("required_skills", [])) or "not specified"
    pref_skills = ", ".join(job_details.get("preferred_skills", [])) or "none listed"

    matching_stories = [
        s for s in story_bank
        if s.get("is_complete") and bullet.lower()[:40] in (s.get("original_bullet") or "").lower()
    ]

    story_block = ""
    if matching_stories:
        s = matching_stories[0]
        story_block = (
            f"\n\nSTAR story for this bullet:\n"
            f"  Situation: {s.get('situation', '—')}\n"
            f"  Task: {s.get('task', '—')}\n"
            f"  Action: {s.get('action', '—')}\n"
            f"  Result: {s.get('result', '—')}"
        )
    else:
        story_block = "\n\nNo STAR story found for this bullet — ask the student for the key detail or metric to use."

    return (
        f"Original bullet: {bullet}\n\n"
        f"Job: {job_details.get('role', '?')} at {job_details.get('company', '?')}\n"
        f"Role type: {job_details.get('role_type', '?')}\n"
        f"Required skills: {req_skills}\n"
        f"Preferred skills: {pref_skills}\n"
        f"Job description: {job_details.get('description', 'not provided')}"
        f"{story_block}"
    )


def run_tailoring_agent(
    bullet: str,
    job_details: dict[str, Any],
    story_bank: list[dict[str, Any]],
    conversation_history: list[dict[str, str]],
    user_message: str,
) -> tuple[str, str | None, str | None, bool]:
    """
    Run one turn of the Resume Bullet Tailoring Agent.

    Args:
        bullet: The original resume bullet being rewritten.
        job_details: Structured output from job_scraping_agent.run_job_scraping_agent().
        story_bank: All completed STAR stories for this user (from db.database).
        conversation_history: Prior turns as {"role": ..., "content": ...} dicts.
        user_message: The user's latest message.

    Returns:
        (response, proposed_bullet, target_skill, is_finalized)
        - response: agent's reply text
        - proposed_bullet: the accepted bullet text if finalized, else None
        - target_skill: the skill being demonstrated if finalized, else None
        - is_finalized: True when the student has accepted a bullet
    """
    context = _build_context_block(bullet, job_details, story_bank)
    system = f"{_SYSTEM_PROMPT}\n\n---\n\n{context}"

    messages = list(conversation_history) + [{"role": "user", "content": user_message}]

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            tools=_TOOLS,
            messages=messages,
        )
    except anthropic.APIError:
        return (
            "I'm having trouble connecting right now. Please try again in a moment.",
            None,
            None,
            False,
        )

    response_text = ""
    proposed_bullet: str | None = None
    target_skill: str | None = None
    is_finalized = False

    for block in response.content:
        if block.type == "text":
            response_text = block.text
        elif block.type == "tool_use" and block.name == "finalize_bullet":
            proposed_bullet = block.input.get("proposed_bullet")
            target_skill = block.input.get("target_skill")
            is_finalized = True
            if not response_text:
                response_text = (
                    "Perfect — bullet locked in. Click **Save Bullet** below to "
                    "add it to this application's tailored bullet set."
                )

    return response_text, proposed_bullet, target_skill, is_finalized
