"""
Resume Bullet Tailoring page — side-by-side conversation UI.

Layout:
  Left column  — bullet selection + chat with the tailoring agent
  Right column — job context panel + saved tailored bullets for this application

Flow:
  1. User picks a job application from their pipeline
  2. User picks (or types) a resume bullet from their resume
  3. Agent asks which skill to demonstrate, then proposes a rewrite grounded
     in the user's STAR story bank
  4. User iterates until satisfied, then accepts → bullet saved to DB
  5. Saved bullets appear in the right panel in recommended order
"""

import uuid

import streamlit as st

from agents.tailoring_agent import run_tailoring_agent
from db.database import (
    create_tailored_bullet,
    get_job_applications_for_user,
    get_star_stories_for_user,
    get_tailored_bullets_for_application,
    get_user,
)
from pages.onboarding import require_user

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _reset_tailoring_conversation() -> None:
    st.session_state["tail_history"] = []
    st.session_state["tail_bullet"] = ""
    st.session_state["tail_pending"] = None  # {"proposed_bullet", "target_skill"}


def _init_state() -> None:
    if "tail_history" not in st.session_state:
        _reset_tailoring_conversation()
    if "tail_app_id" not in st.session_state:
        st.session_state["tail_app_id"] = None


# ---------------------------------------------------------------------------
# Right panel — job context + saved bullets
# ---------------------------------------------------------------------------

def _render_right_panel(app: dict, user_id: str) -> None:
    st.subheader("Job Context")
    st.markdown(f"**{app['company']}** — {app['role']}")
    if app.get("jd_text"):
        with st.expander("Job description"):
            st.write(app["jd_text"])

    st.divider()
    st.subheader("Tailored Bullets")

    bullets = get_tailored_bullets_for_application(app["id"])
    if not bullets:
        st.caption("No bullets saved yet for this application.")
        return

    for i, b in enumerate(bullets, 1):
        with st.container(border=True):
            st.markdown(f"**#{i}** _{b.get('target_skill', '—')}_")
            st.write(b["tailored_bullet"] or b["original_bullet"])
            st.caption(f"Original: {b['original_bullet'][:80]}…")


# ---------------------------------------------------------------------------
# Left panel — bullet selection + chat
# ---------------------------------------------------------------------------

def _render_chat(app: dict, user_id: str) -> None:
    st.subheader("Tailor a Bullet")

    resume_text: str = st.session_state.get("resume_text", "")
    story_bank = get_star_stories_for_user(user_id)

    # --- Bullet selection ---
    active_bullet = st.session_state.get("tail_bullet", "")

    if not active_bullet:
        st.caption("Choose a bullet from your resume or type one manually.")

        bullet_input_method = st.radio(
            "Bullet source",
            ["Type manually", "Pick from resume"],
            horizontal=True,
        )

        if bullet_input_method == "Type manually":
            typed = st.text_area(
                "Resume bullet",
                placeholder="e.g. Led cross-functional team to launch mobile payment feature...",
                height=80,
            )
            if st.button("Start tailoring", type="primary") and typed.strip():
                st.session_state["tail_bullet"] = typed.strip()
                st.rerun()

        else:
            if not resume_text:
                st.warning("No resume text found. Please complete onboarding first.")
                return

            # Split resume into non-empty lines as candidate bullets
            lines = [ln.strip() for ln in resume_text.splitlines() if len(ln.strip()) > 30]
            if not lines:
                st.warning("Couldn't parse individual bullets from your resume. Type one manually.")
                return

            selected = st.selectbox("Select a bullet", options=lines)
            if st.button("Start tailoring", type="primary"):
                st.session_state["tail_bullet"] = selected
                st.rerun()
        return

    # --- Active conversation ---
    st.caption(f"**Bullet:** {active_bullet}")

    # Build job_details dict from the stored application record
    job_details = {
        "company": app.get("company", ""),
        "role": app.get("role", ""),
        "role_type": "",
        "description": app.get("jd_text") or "",
        "required_skills": [],
        "preferred_skills": [],
        "location": None,
    }

    for msg in st.session_state["tail_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- Pending save banner ---
    pending = st.session_state.get("tail_pending")
    if pending:
        st.success("Bullet accepted — ready to save.")
        with st.container(border=True):
            st.markdown(f"**{pending['proposed_bullet']}**")
            st.caption(f"Demonstrates: _{pending['target_skill']}_")

        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("Save Bullet", type="primary"):
                existing = get_tailored_bullets_for_application(app["id"])
                order = len(existing) + 1
                try:
                    create_tailored_bullet(
                        id=str(uuid.uuid4()),
                        application_id=app["id"],
                        original_bullet=active_bullet,
                        tailored_bullet=pending["proposed_bullet"],
                        target_skill=pending["target_skill"],
                        recommended_order=order,
                    )
                    st.success("Saved!")
                    _reset_tailoring_conversation()
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save: {e}")
        with col2:
            if st.button("Keep editing"):
                st.session_state["tail_pending"] = None
                st.rerun()
        return

    # --- Chat input ---
    user_input = st.chat_input("Your response…")
    if user_input:
        st.session_state["tail_history"].append({"role": "user", "content": user_input})

        with st.spinner("Thinking…"):
            response, proposed, skill, finalized = run_tailoring_agent(
                bullet=active_bullet,
                job_details=job_details,
                story_bank=story_bank,
                conversation_history=st.session_state["tail_history"][:-1],
                user_message=user_input,
            )

        st.session_state["tail_history"].append({"role": "assistant", "content": response})

        if finalized and proposed:
            st.session_state["tail_pending"] = {
                "proposed_bullet": proposed,
                "target_skill": skill or "",
            }

        st.rerun()

    if st.button("Start over with a different bullet"):
        _reset_tailoring_conversation()
        st.rerun()


# ---------------------------------------------------------------------------
# Page entrypoint
# ---------------------------------------------------------------------------

def render_page() -> None:
    if not require_user():
        return
    _init_state()
    user_id = st.session_state["user_id"]
    apps = get_job_applications_for_user(user_id)
    if not apps:
        st.warning("No applications found. Add a job in the Job Manager first.")
        return
    app_options = {f"{a['company']} — {a['role']}": a for a in apps}
    selected_label = st.selectbox(
        "Select a job application to tailor bullets for",
        options=list(app_options.keys()),
    )
    selected_app = app_options[selected_label]
    if st.session_state.get("tail_app_id") != selected_app["id"]:
        _reset_tailoring_conversation()
        st.session_state["tail_app_id"] = selected_app["id"]
    st.divider()
    left, right = st.columns([2, 1])
    with left:
        _render_chat(selected_app, user_id)
    with right:
        _render_right_panel(selected_app, user_id)


def main() -> None:
    st.set_page_config(page_title="Bullet Tailoring — RecruitingEdge", layout="wide")
    render_page()


if __name__ == "__main__":
    main()
