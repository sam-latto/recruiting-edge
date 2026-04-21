"""
ATS Resume Scorer page — score dashboard with category breakdown.

Layout:
  Top    — Application selector + Score button
  Middle — Overall score gauge + four category scores side by side
  Bottom — Matched/missing keywords & skills, section feedback, improvement suggestions

The user picks a job application, confirms their resume is loaded, and clicks Score.
The agent runs and writes the result to the DB; the UI then reads it back and
renders the full breakdown. Score history (multiple runs per application) is
preserved — the most recent is shown by default.
"""

import streamlit as st

from agents.ats_agent import run_ats_agent
from db.database import (
    get_ats_scores_for_application,
    get_job_applications_for_user,
)
from pages.onboarding import require_user

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_color(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 50:
        return "orange"
    return "red"


def _render_score_badge(label: str, score: int) -> None:
    color = _score_color(score)
    st.markdown(f":{color}[**{score}**]  {label}")


def _render_tag_list(items: list[str], color: str) -> None:
    if not items:
        st.caption("None")
        return
    tags = " ".join(f":{color}-background[{item}]" for item in items)
    st.markdown(tags)


# ---------------------------------------------------------------------------
# Dashboard sections
# ---------------------------------------------------------------------------

def _render_score_overview(result: dict) -> None:
    overall = result.get("overall_score", 0)
    color = _score_color(overall)

    st.markdown(f"## :{color}[{overall} / 100]  Overall ATS Score")
    st.progress(overall / 100)

    st.divider()

    cols = st.columns(4)
    dimensions = [
        ("Keyword Match", result.get("keyword_score", 0)),
        ("Skills Coverage", result.get("skills_score", 0)),
        ("Experience Alignment", result.get("experience_score", 0)),
        ("Format", result.get("format_score", 0)),
    ]
    for col, (label, score) in zip(cols, dimensions):
        with col:
            c = _score_color(score)
            st.metric(label, f"{score}/100")
            st.progress(score / 100)


def _render_keywords_and_skills(result: dict) -> None:
    st.subheader("Keywords")
    kw_col1, kw_col2 = st.columns(2)
    with kw_col1:
        st.markdown("**Matched**")
        _render_tag_list(result.get("matched_keywords", []), "green")
    with kw_col2:
        st.markdown("**Missing**")
        _render_tag_list(result.get("missing_keywords", []), "red")

    st.subheader("Skills")
    sk_col1, sk_col2 = st.columns(2)
    with sk_col1:
        st.markdown("**Matched**")
        _render_tag_list(result.get("matched_skills", []), "green")
    with sk_col2:
        st.markdown("**Missing**")
        _render_tag_list(result.get("missing_skills", []), "red")


def _render_section_feedback(result: dict) -> None:
    feedback = result.get("section_feedback") or {}
    if not feedback:
        return

    st.subheader("Section Feedback")
    labels = {
        "summary": "Summary",
        "keywords": "Keywords",
        "skills": "Skills",
        "experience": "Experience",
        "format": "Format",
    }
    for key, label in labels.items():
        text = feedback.get(key, "")
        if text:
            st.markdown(f"**{label}:** {text}")


def _render_suggestions(result: dict) -> None:
    suggestions = result.get("improvement_suggestions", [])
    if not suggestions:
        return

    st.subheader("Improvement Suggestions")
    st.caption("Prioritized — address these in order for the biggest score gain.")
    for i, suggestion in enumerate(suggestions, 1):
        st.markdown(f"{i}. {suggestion}")


# ---------------------------------------------------------------------------
# Page entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="ATS Scorer — RecruitingEdge", layout="wide")

    if not require_user():
        return

    user_id = st.session_state["user_id"]
    resume_text: str = st.session_state.get("resume_text", "")

    st.title("ATS Resume Scorer")
    st.caption(
        "Simulates how Workday, Greenhouse, and Lever score your resume: "
        "keyword frequency, skills coverage, title alignment, and format signals — "
        "not holistic judgment. Optimize for what the filter actually does."
    )

    # --- Application selector ---
    apps = get_job_applications_for_user(user_id)
    if not apps:
        st.warning("No applications found. Add a job in the Job Manager first.")
        return

    # Only show apps that have a JD attached
    scoreable = [a for a in apps if a.get("jd_text")]
    unscoreable = [a for a in apps if not a.get("jd_text")]

    if not scoreable:
        st.warning(
            "None of your applications have a job description saved. "
            "Edit a job in the Job Manager and add the JD text, then come back."
        )
        return

    app_options = {f"{a['company']} — {a['role']}": a for a in scoreable}
    selected_label = st.selectbox("Select an application to score against", options=list(app_options.keys()))
    selected_app = app_options[selected_label]

    if unscoreable:
        st.caption(f"{len(unscoreable)} application(s) hidden — no JD text saved.")

    # --- Resume check ---
    if not resume_text.strip():
        st.error("No resume text found in your session. Please re-upload your resume on the onboarding page.")
        return

    st.divider()

    # --- Score button ---
    if st.button("Score my resume against this JD", type="primary"):
        with st.spinner("Scoring… this takes 10–20 seconds."):
            result = run_ats_agent(
                resume_text=resume_text,
                jd_text=selected_app["jd_text"],
                application_id=selected_app["id"],
            )
        st.session_state[f"ats_result_{selected_app['id']}"] = result
        st.rerun()

    # --- Display result ---
    result = st.session_state.get(f"ats_result_{selected_app['id']}")

    # Fall back to most recent DB score if the page was refreshed
    if result is None:
        history = get_ats_scores_for_application(selected_app["id"])
        if history:
            result = history[0]
            st.session_state[f"ats_result_{selected_app['id']}"] = result

    if result:
        _render_score_overview(result)
        st.divider()
        _render_keywords_and_skills(result)
        st.divider()
        _render_section_feedback(result)
        st.divider()
        _render_suggestions(result)

        # Score history
        history = get_ats_scores_for_application(selected_app["id"])
        if len(history) > 1:
            with st.expander(f"Score history ({len(history)} runs)"):
                for h in history:
                    scored_at = h.get("scored_at", "—")
                    st.markdown(f"- **{h['overall_score']}/100** — {scored_at}")
    else:
        st.info("Click the button above to score your resume against this job description.")


if __name__ == "__main__":
    main()
