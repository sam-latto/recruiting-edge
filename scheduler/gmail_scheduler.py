"""
APScheduler daily Gmail scan — runs run_gmail_agent() on a schedule and
persists newly detected applications, skipping duplicates.

The scheduler is started from app.py on Streamlit startup and runs in a
background thread. It does not interact with the UI — it writes silently to
the database so new applications appear the next time the user loads the
tracker page.

Deduplication: application_exists() is called before every insert. The agent
never writes directly — the scheduler is the sole writer for Gmail-sourced
applications, keeping deduplication logic in one place (db/database.py).
"""

import logging
import uuid
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from agents.gmail_agent import run_gmail_agent
from db.database import application_exists, create_job_application

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _scan_and_persist(gmail_service, user_id: str) -> None:
    """Run one Gmail scan and write any new applications found."""
    logger.info("Gmail scan started for user %s", user_id)
    try:
        detected = run_gmail_agent(gmail_service, user_id, lookback_days=7)
    except Exception as e:
        logger.error("Gmail scan failed: %s", e)
        return

    saved = 0
    for app in detected:
        company = app.get("company", "").strip()
        role = app.get("role", "").strip()
        if not company or not role:
            continue
        if application_exists(user_id, company, role):
            continue
        try:
            create_job_application(
                id=str(uuid.uuid4()),
                user_id=user_id,
                company=company,
                role=role,
                date_applied=app.get("date_applied"),
                status="applied",
                source="gmail",
                notes=f"Auto-detected from email: {app.get('email_subject', '')}",
            )
            saved += 1
        except Exception as e:
            logger.error("Failed to save detected application (%s / %s): %s", company, role, e)

    logger.info("Gmail scan complete — %d new application(s) saved", saved)


def start_scheduler(gmail_service, user_id: str) -> None:
    """
    Start the background scheduler if it isn't already running.

    Schedules a daily scan at 08:00 local time. Safe to call multiple times —
    subsequent calls are no-ops if the scheduler is already running.

    Args:
        gmail_service: Authenticated Gmail API service object.
        user_id: RecruitingEdge user ID to scan and persist for.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        func=_scan_and_persist,
        trigger=CronTrigger(hour=8, minute=0),
        args=[gmail_service, user_id],
        id="gmail_daily_scan",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Gmail scheduler started — daily scan at 08:00")


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler. Called on app teardown."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Gmail scheduler stopped")


def run_scan_now(gmail_service, user_id: str) -> int:
    """
    Trigger an immediate scan outside the schedule (used by the UI's
    'Scan now' button). Returns the number of new applications saved.
    """
    before_count = 0  # We measure by counting new saves inside _scan_and_persist
    # Re-implement inline so we can return a count to the UI
    try:
        detected = run_gmail_agent(gmail_service, user_id, lookback_days=30)
    except Exception:
        return 0

    saved = 0
    for app in detected:
        company = app.get("company", "").strip()
        role = app.get("role", "").strip()
        if not company or not role:
            continue
        if application_exists(user_id, company, role):
            continue
        try:
            create_job_application(
                id=str(uuid.uuid4()),
                user_id=user_id,
                company=company,
                role=role,
                date_applied=app.get("date_applied"),
                status="applied",
                source="gmail",
                notes=f"Auto-detected from email: {app.get('email_subject', '')}",
            )
            saved += 1
        except Exception:
            continue

    return saved
