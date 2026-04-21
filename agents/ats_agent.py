"""
ATS Scoring Agent — simulates how an Applicant Tracking System scores a resume
against a job description.

Does NOT: make holistic judgments about candidate quality, rewrite the resume,
or produce output that requires semantic understanding. The simulation is
deliberately mechanical — keyword frequency, skills taxonomy coverage, title
alignment — because that is what real ATS systems (Workday, Greenhouse, Lever)
actually do. Optimizing for semantic similarity gives false confidence; this
agent helps students pass the actual filter.

Writes to the DB directly (ats_scores table) because scoring is a one-shot
operation, not a conversation. The caller does not need to decide what to persist.

Hands off to: pages/ats_scorer.py, which reads the score back from the DB and
renders the dashboard.

Interview-ready design decision: Real ATS systems are not LLMs. They use keyword
frequency, skills taxonomy lookup, and title normalization. This agent replicates
that behavior so students can optimize for what the filter actually does, not for
what sounds most impressive to a human reader.
"""

import uuid
from typing import Any

import anthropic
from anthropic import Anthropic

from db.database import create_ats_score

client = Anthropic()

MODEL = "claude-sonnet-4-6"

_SYSTEM_PROMPT = """You are simulating an Applicant Tracking System (ATS) like Workday, \
Greenhouse, or Lever. Your job is to score a resume against a job description the way \
a real ATS does — mechanically, not holistically.

Real ATS systems do NOT use semantic understanding. They use:
1. Keyword frequency: does the resume contain words that appear in the JD? How often?
2. Skills taxonomy: do the listed skills match the required/preferred skills?
3. Title normalization: does the candidate's most recent title align with the target role?
4. Format signals: are sections clearly labeled? Are there tables or columns that parsers skip?

Score each dimension 0–100 and compute an overall weighted score:
  overall = 0.30 * keyword_score + 0.35 * skills_score + 0.25 * experience_score + 0.10 * format_score

For improvement suggestions, be specific and actionable. Good: "Add 'cross-functional' \
— appears 3x in JD, 0x in resume." Bad: "Add more keywords."

Call the `submit_ats_score` tool with your complete assessment."""

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "submit_ats_score",
        "description": "Submit the complete ATS score and feedback for this resume/JD pair.",
        "input_schema": {
            "type": "object",
            "properties": {
                "overall_score": {
                    "type": "integer",
                    "description": "Weighted composite score 0–100.",
                },
                "keyword_score": {
                    "type": "integer",
                    "description": "Keyword frequency match score 0–100.",
                },
                "skills_score": {
                    "type": "integer",
                    "description": "Required skills coverage score 0–100.",
                },
                "experience_score": {
                    "type": "integer",
                    "description": "Seniority and title alignment score 0–100.",
                },
                "format_score": {
                    "type": "integer",
                    "description": "ATS-parseable formatting signals score 0–100.",
                },
                "matched_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords from the JD found in the resume.",
                },
                "missing_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "High-frequency JD keywords absent from the resume.",
                },
                "matched_skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Required/preferred skills present in the resume.",
                },
                "missing_skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Required/preferred skills absent from the resume.",
                },
                "section_feedback": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "keywords": {"type": "string"},
                        "skills": {"type": "string"},
                        "experience": {"type": "string"},
                        "format": {"type": "string"},
                    },
                    "required": ["summary", "keywords", "skills", "experience", "format"],
                    "description": "One-sentence feedback per scoring dimension.",
                },
                "improvement_suggestions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Prioritized, specific, actionable suggestions.",
                },
            },
            "required": [
                "overall_score", "keyword_score", "skills_score",
                "experience_score", "format_score",
                "matched_keywords", "missing_keywords",
                "matched_skills", "missing_skills",
                "section_feedback", "improvement_suggestions",
            ],
        },
    }
]

_ERROR_SCORE: dict[str, Any] = {
    "overall_score": 0,
    "keyword_score": 0,
    "skills_score": 0,
    "experience_score": 0,
    "format_score": 0,
    "matched_keywords": [],
    "missing_keywords": [],
    "matched_skills": [],
    "missing_skills": [],
    "section_feedback": {
        "summary": "Scoring failed — please try again.",
        "keywords": "",
        "skills": "",
        "experience": "",
        "format": "",
    },
    "improvement_suggestions": ["Scoring failed — please try again."],
    "scrape_success": False,
}


def run_ats_agent(
    resume_text: str,
    jd_text: str,
    application_id: str,
) -> dict[str, Any]:
    """
    Score a resume against a job description and write the result to the DB.

    Args:
        resume_text: Full plain-text content of the candidate's resume.
        jd_text: Full plain-text job description.
        application_id: FK to job_applications — used to write the score record.

    Returns:
        The full score dict (same shape as the ats_scores table row).
        Never raises — returns an error-state dict on any failure.
    """
    if not resume_text.strip() or not jd_text.strip():
        return {**_ERROR_SCORE, "improvement_suggestions": ["Resume or job description text is empty."]}

    prompt = (
        f"Resume:\n{resume_text}\n\n"
        f"---\n\nJob Description:\n{jd_text}"
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            tools=_TOOLS,
            tool_choice={"type": "any"},
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError:
        return {**_ERROR_SCORE, "improvement_suggestions": ["Could not reach the API — please try again."]}

    for block in response.content:
        if block.type == "tool_use" and block.name == "submit_ats_score":
            data = block.input
            score_id = str(uuid.uuid4())
            try:
                create_ats_score(
                    id=score_id,
                    application_id=application_id,
                    overall_score=data["overall_score"],
                    keyword_score=data.get("keyword_score"),
                    skills_score=data.get("skills_score"),
                    experience_score=data.get("experience_score"),
                    format_score=data.get("format_score"),
                    matched_keywords=data.get("matched_keywords", []),
                    missing_keywords=data.get("missing_keywords", []),
                    matched_skills=data.get("matched_skills", []),
                    missing_skills=data.get("missing_skills", []),
                    section_feedback=data.get("section_feedback"),
                    improvement_suggestions=data.get("improvement_suggestions", []),
                )
            except Exception:
                pass  # Score is still returned to the UI even if the DB write fails
            return dict(data)

    return {**_ERROR_SCORE, "improvement_suggestions": ["Scoring returned no result — please try again."]}
