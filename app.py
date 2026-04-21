"""
RecruitingEdge — Streamlit entrypoint.

Wires all pages into a sidebar navigation and initializes shared services
(database, Gmail scheduler) on startup.

Run with:
    streamlit run app.py
"""

import streamlit as st

from db.database import init_db

# Must be the first Streamlit call in the entire app
st.set_page_config(
    page_title="RecruitingEdge",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize DB once per session
if "db_initialized" not in st.session_state:
    init_db()
    st.session_state["db_initialized"] = True

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

_PAGES = {
    "Onboarding": "onboarding",
    "STAR Story Builder": "star_builder",
    "Job Manager": "job_manager",
    "Bullet Tailoring": "tailoring",
    "ATS Scorer": "ats_scorer",
    "Application Tracker": "tracker",
}

with st.sidebar:
    st.title("RecruitingEdge")
    st.caption("AI-powered recruiting command center")
    st.divider()

    # Show user email if logged in
    if "user_email" in st.session_state:
        st.caption(f"Logged in as **{st.session_state['user_email']}**")
        st.divider()

    selected = st.radio(
        "Navigate to",
        options=list(_PAGES.keys()),
        label_visibility="collapsed",
    )

# ---------------------------------------------------------------------------
# Route to selected page
# ---------------------------------------------------------------------------

page_key = _PAGES[selected]

if page_key == "onboarding":
    from pages.onboarding import render
    render()

elif page_key == "star_builder":
    from pages.star_builder import render_page
    st.title("STAR Story Builder")
    render_page()

elif page_key == "job_manager":
    from pages.job_manager import render_page
    st.title("Job Manager")
    render_page()

elif page_key == "tailoring":
    from pages.tailoring import render_page
    st.title("Bullet Tailoring")
    render_page()

elif page_key == "ats_scorer":
    from pages.ats_scorer import render_page
    render_page()  # render_page already calls st.title internally

elif page_key == "tracker":
    from pages.tracker import render_page
    render_page()  # render_page already calls st.title internally

# ---------------------------------------------------------------------------
# Gmail scheduler — start after user is authenticated and credentials exist
# ---------------------------------------------------------------------------

if (
    "user_id" in st.session_state
    and "gmail_scheduler_started" not in st.session_state
):
    from pathlib import Path
    if Path("credentials.json").exists() and Path("token.json").exists():
        try:
            from tools.gmail_client import get_gmail_service
            from scheduler.gmail_scheduler import start_scheduler
            service = get_gmail_service()
            start_scheduler(service, st.session_state["user_id"])
            st.session_state["gmail_scheduler_started"] = True
        except Exception:
            pass  # Scheduler is non-critical; fail silently
