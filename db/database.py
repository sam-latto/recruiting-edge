"""
Database connection management and CRUD operations for all RecruitingEdge tables.

All state in the application lives here. Agents never touch the DB directly —
they return structured data and callers decide what to persist. This keeps agents
testable in isolation and deduplication logic co-located with the schema.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_DB_PATH = os.getenv("DATABASE_PATH", "./recruitingedge.db")
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


@contextmanager
def get_connection():
    """Yield a SQLite connection with foreign keys enforced and row_factory set."""
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    schema = _SCHEMA_PATH.read_text()
    with get_connection() as conn:
        conn.executescript(schema)


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------

def create_user(id: str, email: str) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO users (id, email) VALUES (?, ?)",
            (id, email),
        )
    return get_user(id)


def get_user(id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (id,)).fetchone()
    return dict(row) if row else None


def update_user_resume(id: str, resume_text: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE users SET resume_text = ? WHERE id = ?",
            (resume_text, id),
        )


def delete_user(id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (id,))


# ---------------------------------------------------------------------------
# star_stories
# ---------------------------------------------------------------------------

def create_star_story(
    id: str,
    user_id: str,
    original_bullet: str,
) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO star_stories (id, user_id, original_bullet) VALUES (?, ?, ?)",
            (id, user_id, original_bullet),
        )
    return get_star_story(id)


def get_star_story(id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM star_stories WHERE id = ?", (id,)).fetchone()
    return dict(row) if row else None


def get_star_stories_for_user(user_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM star_stories WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_star_story(
    id: str,
    situation: str | None = None,
    task: str | None = None,
    action: str | None = None,
    result: str | None = None,
    is_complete: bool | None = None,
) -> None:
    fields: list[str] = []
    values: list[Any] = []
    for col, val in [
        ("situation", situation),
        ("task", task),
        ("action", action),
        ("result", result),
        ("is_complete", is_complete),
    ]:
        if val is not None:
            fields.append(f"{col} = ?")
            values.append(val)
    if not fields:
        return
    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE star_stories SET {', '.join(fields)} WHERE id = ?",
            values,
        )


def delete_star_story(id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM star_stories WHERE id = ?", (id,))


# ---------------------------------------------------------------------------
# job_applications
# ---------------------------------------------------------------------------

ApplicationStatus = str  # 'applied' | 'phone_screen' | 'interview' | 'offer' | 'rejected' | 'withdrawn'

def create_job_application(
    id: str,
    user_id: str,
    company: str,
    role: str,
    date_applied: str | None = None,
    status: ApplicationStatus = "applied",
    job_url: str | None = None,
    jd_text: str | None = None,
    notes: str | None = None,
    next_steps: str | None = None,
    source: str = "manual",
) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO job_applications
               (id, user_id, company, role, date_applied, status, job_url, jd_text,
                notes, next_steps, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (id, user_id, company, role, date_applied, status, job_url, jd_text,
             notes, next_steps, source),
        )
    return get_job_application(id)


def get_job_application(id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM job_applications WHERE id = ?", (id,)
        ).fetchone()
    return dict(row) if row else None


def get_job_applications_for_user(user_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM job_applications WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_job_application(id: str, **kwargs: Any) -> None:
    allowed = {
        "company", "role", "date_applied", "status", "job_url",
        "jd_text", "notes", "next_steps", "source",
    }
    fields = [f"{k} = ?" for k in kwargs if k in allowed]
    values = [v for k, v in kwargs.items() if k in allowed]
    if not fields:
        return
    values.append(id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE job_applications SET {', '.join(fields)} WHERE id = ?",
            values,
        )


def delete_job_application(id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM job_applications WHERE id = ?", (id,))


def application_exists(user_id: str, company: str, role: str) -> bool:
    """Deduplication check used by the Gmail agent caller."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM job_applications WHERE user_id = ? AND company = ? AND role = ?",
            (user_id, company, role),
        ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# tailored_bullets
# ---------------------------------------------------------------------------

def create_tailored_bullet(
    id: str,
    application_id: str,
    original_bullet: str,
    tailored_bullet: str | None = None,
    target_skill: str | None = None,
    recommended_order: int | None = None,
) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO tailored_bullets
               (id, application_id, original_bullet, tailored_bullet, target_skill, recommended_order)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (id, application_id, original_bullet, tailored_bullet, target_skill, recommended_order),
        )
    return get_tailored_bullet(id)


def get_tailored_bullet(id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM tailored_bullets WHERE id = ?", (id,)
        ).fetchone()
    return dict(row) if row else None


def get_tailored_bullets_for_application(application_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """SELECT * FROM tailored_bullets WHERE application_id = ?
               ORDER BY recommended_order ASC, created_at ASC""",
            (application_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_tailored_bullet(id: str, **kwargs: Any) -> None:
    allowed = {"tailored_bullet", "target_skill", "recommended_order"}
    fields = [f"{k} = ?" for k in kwargs if k in allowed]
    values = [v for k, v in kwargs.items() if k in allowed]
    if not fields:
        return
    values.append(id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE tailored_bullets SET {', '.join(fields)} WHERE id = ?",
            values,
        )


def delete_tailored_bullet(id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM tailored_bullets WHERE id = ?", (id,))


# ---------------------------------------------------------------------------
# contacts
# ---------------------------------------------------------------------------

def create_contact(
    id: str,
    application_id: str,
    name: str,
    title: str | None = None,
    email: str | None = None,
    linkedin: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO contacts (id, application_id, name, title, email, linkedin, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (id, application_id, name, title, email, linkedin, notes),
        )
    return get_contact(id)


def get_contact(id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM contacts WHERE id = ?", (id,)).fetchone()
    return dict(row) if row else None


def get_contacts_for_application(application_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM contacts WHERE application_id = ?",
            (application_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_contact(id: str, **kwargs: Any) -> None:
    allowed = {"name", "title", "email", "linkedin", "notes"}
    fields = [f"{k} = ?" for k in kwargs if k in allowed]
    values = [v for k, v in kwargs.items() if k in allowed]
    if not fields:
        return
    values.append(id)
    with get_connection() as conn:
        conn.execute(
            f"UPDATE contacts SET {', '.join(fields)} WHERE id = ?",
            values,
        )


def delete_contact(id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM contacts WHERE id = ?", (id,))


# ---------------------------------------------------------------------------
# ats_scores
# ---------------------------------------------------------------------------

def create_ats_score(
    id: str,
    application_id: str,
    overall_score: int,
    keyword_score: int | None = None,
    skills_score: int | None = None,
    experience_score: int | None = None,
    format_score: int | None = None,
    matched_keywords: list[str] | None = None,
    missing_keywords: list[str] | None = None,
    matched_skills: list[str] | None = None,
    missing_skills: list[str] | None = None,
    section_feedback: dict[str, str] | None = None,
    improvement_suggestions: list[str] | None = None,
) -> dict[str, Any]:
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO ats_scores
               (id, application_id, overall_score, keyword_score, skills_score,
                experience_score, format_score, matched_keywords, missing_keywords,
                matched_skills, missing_skills, section_feedback, improvement_suggestions)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                id, application_id, overall_score, keyword_score, skills_score,
                experience_score, format_score,
                json.dumps(matched_keywords) if matched_keywords is not None else None,
                json.dumps(missing_keywords) if missing_keywords is not None else None,
                json.dumps(matched_skills) if matched_skills is not None else None,
                json.dumps(missing_skills) if missing_skills is not None else None,
                json.dumps(section_feedback) if section_feedback is not None else None,
                json.dumps(improvement_suggestions) if improvement_suggestions is not None else None,
            ),
        )
    return get_ats_score(id)


def get_ats_score(id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM ats_scores WHERE id = ?", (id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    for col in ("matched_keywords", "missing_keywords", "matched_skills",
                "missing_skills", "section_feedback", "improvement_suggestions"):
        if result.get(col):
            result[col] = json.loads(result[col])
    return result


def get_ats_scores_for_application(application_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM ats_scores WHERE application_id = ? ORDER BY scored_at DESC",
            (application_id,),
        ).fetchall()
    results = []
    for row in rows:
        r = dict(row)
        for col in ("matched_keywords", "missing_keywords", "matched_skills",
                    "missing_skills", "section_feedback", "improvement_suggestions"):
            if r.get(col):
                r[col] = json.loads(r[col])
        results.append(r)
    return results


def delete_ats_score(id: str) -> None:
    with get_connection() as conn:
        conn.execute("DELETE FROM ats_scores WHERE id = ?", (id,))
