"""
STAR Story Agent — guides users through building a Situation-Task-Action-Result
story for a single resume bullet.

Does NOT: write to the database, manage conversation storage, or produce
formatted resume output. The caller decides when to persist based on user
signals ("save it", "that's good", etc.).

Hands off to: the caller (pages/star_builder.py), which writes to
db/database.py when the user explicitly signals completion. The completed
story bank is later consumed by tailoring_agent.py to ground bullet rewrites
in real experience rather than invented details.

Architecture note: The agent is stateless — it receives the full conversation
history on every call. This makes it trivially testable in isolation and means
the UI layer owns session management, not the agent.
"""

import os
from typing import Any

import anthropic
from anthropic import Anthropic

client = Anthropic()

MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are a career coach helping an MBA student build a STAR story \
(Situation, Task, Action, Result) for one of their resume bullets. Your goal is a \
natural conversation, not a form-filling exercise.

Rules:
- You have the original bullet the student wants to develop. Start by asking an \
open-ended question that invites them to tell you the story.
- Do NOT ask all four STAR questions in order. Read what they've shared and ask \
the most useful follow-up next — sometimes that means asking about the Result \
before the Situation if they've already hinted at it.
- Probe for specifics: numbers, scale, timeline, stakeholders, obstacles. \
Vague answers like "I improved efficiency" should prompt "By how much? Over what timeframe?"
- Keep your replies short. One question at a time.
- When you have strong answers for all four STAR components AND the user signals \
they are done (e.g. "save it", "that's good", "done", "looks good"), call the \
`submit_star_story` tool with the extracted components. Do not call it before \
the user signals completion.
- If the user hasn't signalled completion but you have all four components, you \
may summarize what you have and ask if they'd like to save it.
- Never invent details. Only use what the user has explicitly told you.
- Do not produce a formatted resume bullet. That is the tailoring agent's job."""

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "submit_star_story",
        "description": (
            "Call this tool when the user has explicitly signalled they are done "
            "and you have solid answers for all four STAR components. Extracts the "
            "structured story so the caller can persist it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "situation": {
                    "type": "string",
                    "description": "The context and background — what was happening, why it mattered.",
                },
                "task": {
                    "type": "string",
                    "description": "The specific responsibility or challenge the user owned.",
                },
                "action": {
                    "type": "string",
                    "description": "What the user personally did — concrete steps, decisions, skills used.",
                },
                "result": {
                    "type": "string",
                    "description": "The outcome — quantified wherever possible (%, $, time, scale).",
                },
            },
            "required": ["situation", "task", "action", "result"],
        },
    }
]


def run_star_agent(
    bullet: str,
    conversation_history: list[dict[str, str]],
    user_message: str,
) -> tuple[str, dict[str, str] | None]:
    """
    Run one turn of the STAR Story Agent.

    Args:
        bullet: The original resume bullet being developed into a story.
        conversation_history: List of prior turns as {"role": ..., "content": ...} dicts.
        user_message: The user's latest message in this turn.

    Returns:
        (response, extracted_star) where extracted_star is a dict with keys
        {situation, task, action, result} if the user signalled completion and
        the agent has all four components, otherwise None.
    """
    messages = list(conversation_history) + [{"role": "user", "content": user_message}]

    system = f"{_SYSTEM_PROMPT}\n\nOriginal bullet: {bullet}"

    try:
        api_response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system,
            tools=_TOOLS,
            messages=messages,
        )
    except anthropic.APIError as e:
        return (
            "I'm having trouble connecting right now. Please try again in a moment.",
            None,
        )

    extracted_star: dict[str, str] | None = None
    response_text = ""

    for block in api_response.content:
        if block.type == "text":
            response_text = block.text
        elif block.type == "tool_use" and block.name == "submit_star_story":
            extracted_star = block.input
            if not response_text:
                response_text = (
                    "Great — I've captured your STAR story. Click **Save Story** "
                    "below to add it to your story bank."
                )

    return response_text, extracted_star
