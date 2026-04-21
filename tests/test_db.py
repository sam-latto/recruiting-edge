"""
Smoke test for the database layer.

Creates all tables, inserts one row per table, reads it back, then deletes it.
Run with: python -m pytest tests/test_db.py -v
"""

import os
import tempfile
import uuid

import pytest

# Use a temp file so every get_connection() call shares the same DB.
# SQLite :memory: creates a fresh, empty DB per connection, which breaks init_db().
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_PATH"] = _tmp.name

from db.database import (
    application_exists,
    create_ats_score,
    create_contact,
    create_job_application,
    create_star_story,
    create_tailored_bullet,
    create_user,
    delete_ats_score,
    delete_contact,
    delete_job_application,
    delete_star_story,
    delete_tailored_bullet,
    delete_user,
    get_ats_score,
    get_contact,
    get_job_application,
    get_star_story,
    get_tailored_bullet,
    get_user,
    init_db,
    update_star_story,
    update_user_resume,
)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------

def test_user_crud():
    user_id = uid()
    user = create_user(user_id, "test@example.com")
    assert user["id"] == user_id
    assert user["email"] == "test@example.com"
    assert user["resume_text"] is None

    update_user_resume(user_id, "Experienced PM with 5 years...")
    updated = get_user(user_id)
    assert updated["resume_text"] == "Experienced PM with 5 years..."

    delete_user(user_id)
    assert get_user(user_id) is None


# ---------------------------------------------------------------------------
# star_stories
# ---------------------------------------------------------------------------

def test_star_story_crud():
    user_id = uid()
    create_user(user_id, "star@example.com")

    story_id = uid()
    story = create_star_story(story_id, user_id, "Led cross-functional team of 8.")
    assert story["id"] == story_id
    assert story["is_complete"] == 0  # SQLite stores BOOLEAN as integer

    update_star_story(
        story_id,
        situation="Q3 launch was at risk",
        task="Coordinate across 3 teams",
        action="Ran daily standups and unblocked dependencies",
        result="Shipped 2 weeks early",
        is_complete=True,
    )
    updated = get_star_story(story_id)
    assert updated["situation"] == "Q3 launch was at risk"
    assert updated["is_complete"] == 1

    delete_star_story(story_id)
    assert get_star_story(story_id) is None

    delete_user(user_id)


# ---------------------------------------------------------------------------
# job_applications
# ---------------------------------------------------------------------------

def test_job_application_crud():
    user_id = uid()
    create_user(user_id, "jobs@example.com")

    app_id = uid()
    app = create_job_application(
        app_id, user_id, "Acme Corp", "Product Manager",
        date_applied="2026-04-20", source="manual",
    )
    assert app["company"] == "Acme Corp"
    assert app["status"] == "applied"

    assert application_exists(user_id, "Acme Corp", "Product Manager")
    assert not application_exists(user_id, "Acme Corp", "Engineer")

    delete_job_application(app_id)
    assert get_job_application(app_id) is None

    delete_user(user_id)


# ---------------------------------------------------------------------------
# tailored_bullets
# ---------------------------------------------------------------------------

def test_tailored_bullet_crud():
    user_id = uid()
    create_user(user_id, "bullets@example.com")
    app_id = uid()
    create_job_application(app_id, user_id, "Beta Inc", "Analyst")

    bullet_id = uid()
    bullet = create_tailored_bullet(
        bullet_id, app_id,
        "Managed data pipeline serving 50K users",
        tailored_bullet="Optimized ETL pipeline, reducing latency by 40%",
        target_skill="data engineering",
        recommended_order=1,
    )
    assert bullet["target_skill"] == "data engineering"

    fetched = get_tailored_bullet(bullet_id)
    assert fetched["recommended_order"] == 1

    delete_tailored_bullet(bullet_id)
    assert get_tailored_bullet(bullet_id) is None

    delete_job_application(app_id)
    delete_user(user_id)


# ---------------------------------------------------------------------------
# contacts
# ---------------------------------------------------------------------------

def test_contact_crud():
    user_id = uid()
    create_user(user_id, "contacts@example.com")
    app_id = uid()
    create_job_application(app_id, user_id, "Gamma LLC", "Consultant")

    contact_id = uid()
    contact = create_contact(
        contact_id, app_id, "Jane Smith",
        title="Head of Recruiting",
        email="jane@gamma.com",
        linkedin="https://linkedin.com/in/janesmith",
    )
    assert contact["name"] == "Jane Smith"

    fetched = get_contact(contact_id)
    assert fetched["email"] == "jane@gamma.com"

    delete_contact(contact_id)
    assert get_contact(contact_id) is None

    delete_job_application(app_id)
    delete_user(user_id)


# ---------------------------------------------------------------------------
# ats_scores
# ---------------------------------------------------------------------------

def test_ats_score_crud():
    user_id = uid()
    create_user(user_id, "ats@example.com")
    app_id = uid()
    create_job_application(app_id, user_id, "Delta Co", "PM")

    score_id = uid()
    score = create_ats_score(
        score_id, app_id,
        overall_score=72,
        keyword_score=68,
        skills_score=75,
        experience_score=80,
        format_score=65,
        matched_keywords=["product roadmap", "stakeholder management"],
        missing_keywords=["agile", "scrum"],
        matched_skills=["SQL", "Python"],
        missing_skills=["Tableau"],
        section_feedback={
            "summary": "Strong summary, missing quantified impact.",
            "keywords": "Add 'agile' — appears 4x in JD.",
            "skills": "Missing Tableau listed as required.",
            "experience": "Title alignment is good.",
            "format": "Avoid tables — ATS parsers skip them.",
        },
        improvement_suggestions=[
            "Add 'agile' — appears 4x in JD, 0x in resume",
            "Add 'scrum' — appears 3x in JD, 0x in resume",
        ],
    )
    assert score["overall_score"] == 72
    assert "agile" in score["missing_keywords"]
    assert isinstance(score["section_feedback"], dict)

    fetched = get_ats_score(score_id)
    assert fetched["improvement_suggestions"][0].startswith("Add 'agile'")

    delete_ats_score(score_id)
    assert get_ats_score(score_id) is None

    delete_job_application(app_id)
    delete_user(user_id)
