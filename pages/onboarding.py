"""
Onboarding page — resume upload and first-run user setup.

Collects the user's email, parses their uploaded resume PDF, and writes a
user record to the database. Stores user_id in st.session_state so all other
pages can access it without re-querying.

This page renders itself automatically when no user_id is found in session state.
"""

import uuid

import streamlit as st

from db.database import create_user, get_user, init_db, update_user_resume
from tools.pdf_parser import extract_text_from_pdf_bytes


def _ensure_db() -> None:
    if "db_initialized" not in st.session_state:
        init_db()
        st.session_state["db_initialized"] = True


def render() -> None:
    """Render the onboarding flow. Call this from pages that require a logged-in user."""
    _ensure_db()

    st.title("Welcome to RecruitingEdge")
    st.write(
        "Let's get you set up. Enter your email and upload your resume to get started."
    )

    with st.form("onboarding_form"):
        email = st.text_input("Email address", placeholder="you@example.com")
        resume_file = st.file_uploader("Upload your resume (PDF)", type=["pdf"])
        submitted = st.form_submit_button("Get started")

    if submitted:
        if not email or "@" not in email:
            st.error("Please enter a valid email address.")
            return
        if resume_file is None:
            st.error("Please upload your resume as a PDF.")
            return

        try:
            resume_text = extract_text_from_pdf_bytes(resume_file.read())
        except ValueError as e:
            st.error(f"Could not read your PDF: {e}")
            return

        if not resume_text.strip():
            st.error(
                "The PDF appears to be empty or image-only. "
                "Please upload a text-based PDF."
            )
            return

        user_id = str(uuid.uuid4())
        try:
            create_user(user_id, email)
            update_user_resume(user_id, resume_text)
        except Exception as e:
            st.error(f"Failed to save your profile: {e}")
            return

        st.session_state["user_id"] = user_id
        st.session_state["user_email"] = email
        st.session_state["resume_text"] = resume_text
        st.success("Profile created! Loading your workspace...")
        st.rerun()


def require_user() -> bool:
    """
    Return True if a user is in session state, False otherwise.

    Pages should call this at the top and gate their content:
        if not require_user():
            return
    """
    _ensure_db()

    if "user_id" not in st.session_state:
        render()
        return False
    return True
